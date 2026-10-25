from datetime import datetime, timedelta

from sqlalchemy import select, update, case, or_, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.models import Task, TaskStatus, Priority, ResultStatus


class TasksRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_task_id(self, task_id: str) -> Task | None:
        stmt = select(Task).where(Task.task_id == task_id)
        return await self.session.scalar(stmt)

    async def create_task(
        self,
        task_id: str,
        query: str,
        priority: Priority,
        callback_url: str,
    ) -> Task:
        stmt = (
            insert(Task)
            .values(
                task_id=task_id,
                query=query,
                priority=priority,
                callback_url=callback_url,
                status=TaskStatus.pending,
                attempts=0,
                callback_attempts=0,
            )
            .on_conflict_do_nothing(
                index_elements=[Task.task_id],
            )
        )

        await self.session.execute(stmt)

        return await self.get_by_task_id(task_id)

    async def take_next_task(self) -> Task | None:
        priority_order = case(
            (Task.priority == Priority.high, 0),
            else_=1,
        )

        next_task_id = (
            select(Task.id)
            .where(Task.status == TaskStatus.pending)
            .order_by(priority_order, Task.id.asc())
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            update(Task)
            .where(
                Task.id == next_task_id,
                Task.status == TaskStatus.pending,
            )
            .values(
                status=TaskStatus.running,
                started_at=datetime.now(),
            )
            .returning(Task)
        )

        result = await self.session.scalars(stmt)
        return result.one_or_none()

    async def finish_task(
            self,
            task_id: int,
            result_status: ResultStatus,
            attempts: int,
            result: list[dict] | None = None,
            error: str | None = None,
    ) -> bool:
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.running,
            )
            .values(
                status=TaskStatus.completed,
                result_status=result_status,
                attempts=attempts,
                result=result if result is not None else [],
                error=error,
                finished_at=datetime.now(),
                next_callback_at=None,
            )
            .returning(Task.id)
        )

        return await self.session.scalar(stmt) is not None

    async def get_callback_task(self) -> Task | None:
        now = datetime.now()

        stmt = (
            select(Task)
            .where(
                Task.status == TaskStatus.completed,
                or_(
                    Task.next_callback_at.is_(None),
                    Task.next_callback_at <= now,
                ),
            )
            .order_by(Task.id.asc())
            .limit(1)
        )

        return await self.session.scalar(stmt)

    async def mark_delivered(self, task_id: int) -> None:
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.completed,
            )
            .values(
                status=TaskStatus.delivered,
                delivered_at=datetime.now(),
                callback_attempts=Task.callback_attempts + 1,
            )
        )

        await self.session.execute(stmt)

    async def schedule_callback_retry(
        self,
        task_id: int,
        delay_seconds: int = 15,
    ) -> None:
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.completed,
            )
            .values(
                callback_attempts=Task.callback_attempts + 1,
                next_callback_at=(
                    datetime.now() + timedelta(seconds=delay_seconds)
                ),
            )
        )

        await self.session.execute(stmt)

    async def reset_running_tasks(self) -> None:
        stmt = (
            update(Task)
            .where(Task.status == TaskStatus.running)
            .values(
                status=TaskStatus.pending,
                started_at=None,
            )
        )

        await self.session.execute(stmt)

    async def get_next_callback_at(self) -> datetime | None:
        stmt = (
            select(func.min(Task.next_callback_at))
            .where(
                Task.status == TaskStatus.completed,
                Task.next_callback_at.is_not(None),
            )
        )

        return await self.session.scalar(stmt)