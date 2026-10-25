import asyncio
from decimal import Decimal

from common.db.models import ResultStatus
from common.queue_worker import ParseResult
from common.schemas import ParserOffer


async def parse(query: str) -> ParseResult:
    await asyncio.sleep(2)

    return ParseResult(
        status=ResultStatus.found,
        attempts=1,
        offers=[
            ParserOffer(
                name=f"DNS: {query}",
                price=Decimal("15990.00"),
                url="https://www.dns-shop.ru/",
            ),
        ],
    )