from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status

from common.db.init import init_db
from common.db.session import create_db_session
from common.db.repositories.tasks import TasksRepository
from common.queue_worker import QueueWorker
from common.callback_worker import CallbackWorker
from common.schemas import TaskRequest, TaskResponse

from onlinetrade.parser import parse


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "onlinetrade.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = create_db_session(
        f"sqlite+aiosqlite:///{DATABASE_PATH}"
    )

    await init_db(engine)

    callback_worker = CallbackWorker(
        session_factory=session_factory,
    )

    queue_worker = QueueWorker(
        session_factory=session_factory,
        parser=parse,
        callback_wake=callback_worker.wake,
    )

    app.state.session_factory = session_factory
    app.state.queue_worker = queue_worker

    await callback_worker.start()
    await queue_worker.start()

    try:
        yield
    finally:
        await queue_worker.stop()
        await callback_worker.stop()
        await engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.post(
    "/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TaskResponse,
)
async def create_task(
    payload: TaskRequest,
    request: Request,
):
    async with request.app.state.session_factory() as session:
        async with session.begin():
            repo = TasksRepository(session)

            task = await repo.create_task(
                task_id=payload.task_id,
                query=payload.query,
                priority=payload.priority,
                callback_url=payload.callback_url,
            )

            if (
                task.query != payload.query
                or task.priority != payload.priority
                or task.callback_url != payload.callback_url
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Task ID already exists with different parameters",
                )

    request.app.state.queue_worker.wake()

    return TaskResponse(task_id=task.task_id)