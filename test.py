
import asyncio
from pathlib import Path
from urllib.parse import quote

from mcp_core.transport.chrome_cdp import get_context


async def main():
    queries = [
        "ryzen 5 5600",
        "kingston nv3 1tb",
        "intel core i5 12400f",
    ]

    async with get_context() as context:
        page = await context.new_page()

        try:
            for query in queries:
                url = (
                    "https://www.onlinetrade.ru/sitesearch.html"
                    f"?query={quote(query)}"
                )

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                if query == "ryzen 5 5600":
                    Path("search.html").write_text(
                        await page.content(),
                        encoding="utf-8",
                    )

                html = await page.content()

                print(
                    query,
                    len(html),
                    await page.title(),
                    "js-challenge-loader" in html,
                )

        finally:
            await page.close()


asyncio.run(main())
