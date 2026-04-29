import pytest

from shortlist.sources.scraped._browser import headless_context


@pytest.mark.browser
@pytest.mark.asyncio
async def test_headless_context_loads_about_blank():
    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("about:blank")
        title = await page.title()
        assert title == ""


@pytest.mark.browser
@pytest.mark.asyncio
async def test_navigator_webdriver_is_undefined():
    async with headless_context() as ctx:
        page = await ctx.new_page()
        await page.goto("about:blank")
        is_webdriver = await page.evaluate("navigator.webdriver")
        assert is_webdriver is None  # patched away
