import asyncio
import logging
from typing import Literal

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from mcp_core.transport.chrome_cdp import get_context

logger = logging.getLogger(__name__)

STORE_URLS = {
    "dns": "https://www.dns-shop.ru/",
    "citilink": "https://www.citilink.ru/",
}


async def warmup(
    store: Literal["dns", "citilink"],
    wait_seconds: float = 40,
) -> None:
    url = STORE_URLS[store]

    logger.info("Starting %s warmup", store)

    async with get_context() as context:
        page = await context.new_page()

        try:
            try:
                await page.goto(
                    url,
                    wait_until="commit",
                    timeout=20_000,
                )
            except PlaywrightTimeoutError:
                logger.warning(
                    "%s navigation timed out, continuing warmup",
                    store,
                )

            await asyncio.sleep(wait_seconds)

        finally:
            await page.close()

    logger.info("%s warmup completed", store)