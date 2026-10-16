"""Recognising Cloudflare's bot-check page, so a source can stop early."""

from __future__ import annotations

import asyncio

from shortlist.sources._browser import on_bot_check


class _Page:
    def __init__(self, title: str) -> None:
        self._title = title

    async def title(self) -> str:
        return self._title


def test_cloudflare_interstitial_is_a_bot_check() -> None:
    assert asyncio.run(on_bot_check(_Page("Just a moment..."))) is True  # type: ignore[arg-type]


def test_results_page_is_not_a_bot_check() -> None:
    page = _Page("French Teacher Jobs, Employment in Brunswick, GA | Indeed")
    assert asyncio.run(on_bot_check(page)) is False  # type: ignore[arg-type]
