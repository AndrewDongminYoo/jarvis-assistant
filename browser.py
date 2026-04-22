# browser.py — Playwright-based web browsing for JARVIS
from typing import Optional

from playwright.async_api import Browser, async_playwright

_browser: Optional[Browser] = None
_pw = None


async def _get_browser() -> Browser:
    global _browser, _pw
    if _browser is None or not _browser.is_connected():
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=True)
    return _browser


async def browse_url(url: str, max_chars: int = 3000) -> str:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        text = await page.inner_text("body")
        return text[:max_chars]
    except Exception as e:
        return f"Failed to load {url}: {e}"
    finally:
        await page.close()


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        encoded = query.replace(" ", "+")
        await page.goto(
            f"https://duckduckgo.com/html/?q={encoded}",
            timeout=15000,
            wait_until="domcontentloaded",
        )
        results: list[dict] = []
        for item in (await page.query_selector_all(".result"))[:max_results]:
            title_el = await item.query_selector(".result__title")
            url_el = await item.query_selector(".result__url")
            snippet_el = await item.query_selector(".result__snippet")
            results.append(
                {
                    "title": await title_el.inner_text() if title_el else "",
                    "url": await url_el.inner_text() if url_el else "",
                    "snippet": await snippet_el.inner_text() if snippet_el else "",
                }
            )
        return results
    except Exception as e:
        return [{"title": "Error", "url": "", "snippet": str(e)}]
    finally:
        await page.close()


async def search_summary(query: str) -> str:
    results = await search_web(query)
    if not results:
        return f"No results found for: {query}"
    return "\n\n".join(
        f"- {r['title']}\n  {r['snippet']}\n  {r['url']}" for r in results
    )
