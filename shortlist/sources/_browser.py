"""Playwright browser context with anti-detection patches.

Async API. Use as:

    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("https://...")

The init script runs in every page created from the context, before any
site code, and patches navigator.webdriver, navigator.languages, etc.
This is best-effort — modern bot-detection (Cloudflare, Datadome,
PerimeterX) layers behavioral fingerprinting on top of these basics.
Sites WILL still detect us; the cooldown layer (T6) handles that.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

# User agent close to default Chrome on Linux x86_64. Update yearly.
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Init script: patch known automation tells. Runs before any site JS on
# every page. Keep small and well-tested.
_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {
    get: () => [{name: 'Chrome PDF Viewer'}, {name: 'Native Client'}]
});
window.chrome = window.chrome || {runtime: {}};
const origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (origQuery) {
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(p)
    );
}
"""


@asynccontextmanager
async def headless_context(
    *,
    user_agent: str = _UA,
    timeout_ms: int = 30_000,
) -> AsyncIterator[BrowserContext]:
    """Launch a stealth-patched Chromium context. Always headless."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(_STEALTH_INIT)
        context.set_default_timeout(timeout_ms)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def on_bot_check(page: Page) -> bool:
    """True when the page is Cloudflare's "Just a moment..." bot check.

    Sources call this after a search fails to load and stop their remaining
    searches: once a site starts challenging, every later request in the run
    is challenged too, and each one would otherwise wait out a full timeout.
    """
    return (await page.title()).strip().lower().startswith("just a moment")
