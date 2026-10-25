from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Priority(Enum):
    high = "high"
    low = "low"


class TaskStatus(Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    delivered = "delivered"


class ResultStatus(Enum):
    found = "found"
    not_found = "not_found"
    failed = "failed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    task_id: Mapped[str] = mapped_column(
        String,
        unique=True,
    )

    query: Mapped[str] = mapped_column(String)
    callback_url: Mapped[str] = mapped_column(String)

    priority: Mapped[Priority] = mapped_column(
        SQLEnum(Priority),
    )

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus),
        default=TaskStatus.pending,
    )

    result_status: Mapped[ResultStatus | None] = mapped_column(
        SQLEnum(ResultStatus),
    )

    result: Mapped[list[dict] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String)

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    callback_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)

    next_callback_at: Mapped[datetime | None] = mapped_column(DateTime)