import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Literal

from fastmcp.exceptions import ToolError

from common.db.models import ResultStatus
from common.queue_worker import ParseResult
from common.schemas import ParserOffer
from common.warmup import warmup

logger = logging.getLogger(__name__)

Store = Literal["dns", "citilink"]
WARMUP_COOLDOWN_SECONDS = 600
_last_warmup_at: dict[str, float] = {}


def _needs_warmup(exc: ToolError) -> bool:
    try:
        detail = json.loads(str(exc))
    except (ValueError, TypeError):
        return False

    if not isinstance(detail, dict):
        return False

    error_code = detail.get("error")
    if error_code in ("challenge_required", "timeout"):
        return True

    if error_code == "transport_down":
        message = detail.get("message")
        return isinstance(message, str) and re.search(
            r"navigation blocked\s*\(HTTP (?:401|403)\)",
            message,
            flags=re.IGNORECASE,
        ) is not None

    return False


async def parse_with_connector(
    query: str,
    search: Callable[[str], Awaitable[Any]],
    *,
    store: Store,
) -> ParseResult:

    attempts = 0

    try:
        for attempt in range(2):
            attempts += 1

            try:
                response = await search(query)
                break

            except Exception as search_error:
                if attempt == 1:
                    raise

                logger.warning(
                    "%s search attempt %s failed for %r: %s",
                    store, attempts, query, search_error,
                )

                if isinstance(search_error, ToolError) and _needs_warmup(search_error):
                    now = time.monotonic()
                    last_warmup = _last_warmup_at.get(store)

                    if last_warmup is None or now - last_warmup >= WARMUP_COOLDOWN_SECONDS:
                        _last_warmup_at[store] = now

                        try:
                            await warmup(store, wait_seconds=40)
                        except Exception:
                            logger.exception("%s warmup failed", store)

        if response.status != "success":
            raise RuntimeError(f"Connector returned status: {response.status}")

        if not response.items:
            return ParseResult(
                status=ResultStatus.not_found,
                attempts=attempts,
            )

        offers = [
            ParserOffer(
                name=item.title,
                price=Decimal(str(item.price_rub)),
                url=item.url,
            )
            for item in response.items
            if item.title
            and item.url
            and item.price_rub is not None
            and item.price_rub > 0
        ]

        if not offers:
            return ParseResult(
                status=ResultStatus.failed,
                attempts=attempts,
                error="Connector returned no valid priced offers",
            )

        return ParseResult(
            status=ResultStatus.found,
            attempts=attempts,
            offers=offers,
        )

    except Exception as exc:
        logger.exception("%s search failed for query %r", store, query)
        return ParseResult(
            status=ResultStatus.failed,
            attempts=attempts,
            error=f"{type(exc).__name__}: {exc}",
        )
