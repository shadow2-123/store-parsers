from dns_connector.server import dns_search

from common.connector_adapter import parse_with_connector
from common.queue_worker import ParseResult


async def parse(query: str) -> ParseResult:
    return await parse_with_connector(
        query=query,
        search=dns_search,
        store="dns"
    )