import asyncio
from decimal import Decimal

from common.db.models import ResultStatus
from common.queue_worker import ParseResult
from common.schemas import ParserOffer


async def parse(query: str) -> ParseResult:
    await asyncio.sleep(2)

    return ParseResult(
        status=ResultStatus.not_found,
        attempts=1
    )