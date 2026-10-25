from sqlalchemy.ext.asyncio import AsyncEngine

from common.db.models import Base


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)