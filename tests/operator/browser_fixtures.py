"""Isolated headless fixture; never uses the user's browser, profile, or CDP."""
import pytest_asyncio
from playwright.async_api import async_playwright

from uni.browser_session import BrowserSession


@pytest_asyncio.fixture
async def local_browser():
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        session = BrowserSession(headless=True, agent_cursor_enabled=False)
        session._context, session._browser, session._page = context, browser, page
        try:
            yield session, page
        finally:
            await context.close()
            await browser.close()
