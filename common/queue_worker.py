import asyncio
import logging

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.db.models import Task, ResultStatus
from common.db.repositories.tasks import TasksRepository
from common.schemas import ParserOffer


logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    status: ResultStatus
    attempts: int
    offers: list[ParserOffer] = field(default_factory=list)
    error: str | None = None


class QueueWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        parser: Callable[[str], Awaitable[ParseResult]],
        callback_wake: Callable[[], None],
    ):
        self.session_factory = session_factory
        self.parser = parser
        self.callback_wake = callback_wake

        self.event = asyncio.Event()
        self.worker: asyncio.Task | None = None

    async def start(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await TasksRepository(session).reset_running_tasks()

        self.worker = asyncio.create_task(self._run())
        self.wake()

    async def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(
                self.worker,
                return_exceptions=True,
            )

    def wake(self) -> None:
        self.event.set()

    async def _take_next_task(self) -> Task | None:
        async with self.session_factory() as session:
            async with session.begin():
                return await TasksRepository(session).take_next_task()

    async def _process_task(self, task: Task) -> None:
        result = await self.parser(task.query)

        offers = [
            offer.model_dump(mode="json")
            for offer in result.offers
        ]

        while True:
            try:
                async with self.session_factory() as session:
                    async with session.begin():
                        saved = await TasksRepository(session).finish_task(
                            task_id=task.id,
                            result_status=result.status,
                            attempts=result.attempts,
                            result=offers,
                            error=result.error,
                        )

                if saved:
                    self.callback_wake()

                return

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Failed to save task result: %s",
                    task.task_id,
                )
                await asyncio.sleep(15)

    async def _run(self) -> None:
        while True:
            await self.event.wait()
            self.event.clear()

            while True:
                try:
                    task = await self._take_next_task()

                    if task is None:
                        break

                    await self._process_task(task)

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception("Queue worker error")
                    await asyncio.sleep(15)