import asyncio
import random
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_from_bytes, urljoin

from bs4 import BeautifulSoup
from mcp_core.transport.chrome_cdp import get_context

from common.db.models import ResultStatus
from common.queue_worker import ParseResult
from common.schemas import ParserOffer


logger = logging.getLogger(__name__)

BASE_URL = "https://www.onlinetrade.ru"
SEARCH_URL = f"{BASE_URL}/sitesearch.html"
MAX_ATTEMPTS = 2
SEARCH_DELAY_RANGE = (3.0, 6.0)

def parse_html(html: str) -> tuple[list[ParserOffer], int]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".goods__items .indexGoods__item")

    offers: list[ParserOffer] = []

    for card in cards:
        title_tag = card.select_one(".indexGoods__item__name[href]")
        price_tag = card.select_one(".indexGoods__item__price .price")

        if title_tag is None or price_tag is None:
            logger.warning("OnlineTrade: карточка без названия или цены")
            continue

        name = re.sub(
            r"\s+", " ",
            title_tag.get_text("", strip=False),
        ).strip()

        href = title_tag.get("href", "").strip()

        price_text = re.sub(
            r"[\s\u00a0\u202f]",
            "",
            price_tag.get_text(" ", strip=True),
        )
        price_text = re.sub(
            r"[^\d,.]", "", price_text
        ).replace(",", ".")

        try:
            price = Decimal(price_text)
        except (InvalidOperation, ValueError):
            logger.warning("OnlineTrade: некорректная цена")
            continue

        if not name or not href or price <= 0:
            logger.warning("OnlineTrade: неполная карточка %r", name)
            continue

        offers.append(
            ParserOffer(
                name=name,
                price=price,
                url=urljoin(BASE_URL, href),
            )
        )

    return offers, len(cards)


async def _load_search_html(query: str) -> tuple[str, bool]:
    encoded_query = quote_from_bytes(query.encode("cp1251"))
    url = f"{SEARCH_URL}?query={encoded_query}"
    await asyncio.sleep(random.uniform(*SEARCH_DELAY_RANGE))
    async with get_context() as context:
        page = await context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            html = await page.content()

            if (
                "js-challenge-loader" in html
                or "servicepipe.tech/loaders/" in html
            ):
                raise RuntimeError("OnlineTrade: anti-bot challenge")

            if not await page.locator(".pageSearch").count():
                raise RuntimeError("OnlineTrade: unexpected search page")

            empty_visible = await page.locator(
                "#js__trueStringBlock"
            ).is_visible()

            logger.info(
                "OnlineTrade: query=%r, html_length=%d",
                query,
                len(html),
            )

            return html, empty_visible

        finally:
            await page.close()


async def parse(query: str) -> ParseResult:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            html, empty_visible = await _load_search_html(query)
            offers, card_count = parse_html(html)

            if offers:
                return ParseResult(
                    status=ResultStatus.found,
                    attempts=attempt,
                    offers=offers,
                )

            if card_count == 0 and empty_visible:
                return ParseResult(
                    status=ResultStatus.not_found,
                    attempts=attempt,
                )

            raise RuntimeError(
                "OnlineTrade: no valid offers "
                f"(cards={card_count}, empty_visible={empty_visible})"
            )

        except Exception as exc:
            logger.warning(
                "OnlineTrade: attempt %d/%d failed for %r: %s",
                attempt,
                MAX_ATTEMPTS,
                query,
                exc,
                exc_info=True,
            )

            if attempt == MAX_ATTEMPTS:
                return ParseResult(
                    status=ResultStatus.failed,
                    attempts=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )

    raise AssertionError("unreachable")