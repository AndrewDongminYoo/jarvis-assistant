import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import browser  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def test_search_summary_returns_no_results_message(monkeypatch):
    async def fake_search(query, max_results=5):
        return []

    monkeypatch.setattr(browser, "search_web", fake_search)
    msg = run(browser.search_summary("anything"))
    assert "No results found for: anything" == msg  # nosec B101


def test_search_summary_formats_each_hit(monkeypatch):
    fake_results = [
        {
            "title": "Example A",
            "url": "https://a.example",
            "snippet": "first snippet",
        },
        {
            "title": "Example B",
            "url": "https://b.example",
            "snippet": "second snippet",
        },
    ]

    async def fake_search(query, max_results=5):
        return fake_results

    monkeypatch.setattr(browser, "search_web", fake_search)
    msg = run(browser.search_summary("query"))

    assert "- Example A" in msg  # nosec B101
    assert "- Example B" in msg  # nosec B101
    assert "https://a.example" in msg  # nosec B101
    assert "first snippet" in msg  # nosec B101
    assert msg.count("- ") == 2  # nosec B101
