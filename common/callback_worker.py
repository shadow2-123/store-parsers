import asyncio
import logging

from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.db.models import Task
from common.db.repositories.tasks import TasksRepository


logger = logging.getLogger(__name__)


class CallbackWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.session_factory = session_factory
        self.client = httpx.AsyncClient(timeout=10.0)

        self.event = asyncio.Event()
        self.worker: asyncio.Task | None = None

    async def start(self) -> None:
        self.worker = asyncio.create_task(
            self._run(),
            name="callback-worker",
        )
        self.wake()

    async def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(
                self.worker,
                return_exceptions=True,
            )

        await self.client.aclose()

    def wake(self) -> None:
        self.event.set()

    async def _get_task(self) -> Task | None:
        async with self.session_factory() as session:
            repo = TasksRepository(session)
            return await repo.get_callback_task()

    async def _get_next_retry_delay(self) -> float | None:
        async with self.session_factory() as session:
            repo = TasksRepository(session)
            next_at = await repo.get_next_callback_at()

        if next_at is None:
            return None

        return max(
            0.0,
            (next_at - datetime.now()).total_seconds(),
        )

    async def _send_callback(self, task: Task) -> None:
        try:
            if task.result_status is None:
                raise ValueError("Task has no result_status")

            response = await self.client.post(
                task.callback_url,
                json={
                    "task_id": task.task_id,
                    "status": task.result_status.value,
                    "offers": task.result or [],
                    "error": task.error,
                },
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise RuntimeError(
                    f"Unexpected response: {response.status_code}"
                )

            data = response.json()

            if (
                data.get("task_id") != task.task_id
                or data.get("status") != "received"
            ):
                raise RuntimeError("Invalid callback response")

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Failed to deliver callback: %s",
                task.task_id,
            )

            async with self.session_factory() as session:
                async with session.begin():
                    await TasksRepository(
                        session
                    ).schedule_callback_retry(
                        task_id=task.id,
                        delay_seconds=15,
                    )

            return

        async with self.session_factory() as session:
            async with session.begin():
                await TasksRepository(session).mark_delivered(
                    task.id,
                )

        logger.info(
            "Callback delivered: %s",
            task.task_id,
        )

    async def _run(self) -> None:
        while True:
            self.event.clear()

            try:
                task = await self._get_task()

                if task is not None:
                    await self._send_callback(task)
                    continue

                delay = await self._get_next_retry_delay()

                if delay is None:
                    await self.event.wait()
                else:
                    try:
                        await asyncio.wait_for(
                            self.event.wait(),
                            timeout=delay,
                        )
                    except asyncio.TimeoutError:
                        pass

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception("Callback worker error")
                await asyncio.sleep(15)