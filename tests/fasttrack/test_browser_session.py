from __future__ import annotations

import asyncio

from uni.browser_session import BrowserSession


class _Page:
    def is_closed(self):
        return False


class _Context:
    def __init__(self):
        self.pages = [_Page()]
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class _Browser:
    def __init__(self, connected=True):
        self.connected = connected

    def is_connected(self):
        return self.connected


class _Playwright:
    def __init__(self):
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


def test_cdp_context_is_alive_without_private_playwright_fields() -> None:
    session = BrowserSession(cdp_url="http://127.0.0.1:9222")
    context = _Context()
    session._context = context
    session._browser = _Browser(connected=True)

    asyncio.run(session.ensure_alive())

    assert session._context is context
    assert context.close_calls == 0


def test_closing_cdp_session_disconnects_without_closing_user_context() -> None:
    session = BrowserSession(cdp_url="http://127.0.0.1:9222")
    context = _Context()
    playwright = _Playwright()
    session._context = context
    session._browser = _Browser(connected=True)
    session._playwright = playwright
    session._owns_context = False

    asyncio.run(session.close())

    assert context.close_calls == 0
    assert playwright.stop_calls == 1


def test_closing_owned_context_closes_it() -> None:
    session = BrowserSession()
    context = _Context()
    session._context = context
    session._playwright = _Playwright()
    session._owns_context = True

    asyncio.run(session.close())

    assert context.close_calls == 1
