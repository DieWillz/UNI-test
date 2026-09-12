from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from uuid import uuid4

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright


class BrowserSession:
    """One persistent visible browser context shared by browser-domain adapters."""

    def __init__(
        self,
        *,
        headless: bool = False,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        channel: str | None = "chrome",
        user_data_dir: str = ".uni-browser-profile",
        search_engine: str = "https://www.bing.com/search?q={query}",
        image_search_engine: str = "https://yandex.ru/images/search?text={query}",
        cdp_url: str | None = None,
        agent_cursor_enabled: bool = True,
        agent_cursor_label: str = "UNI",
        agent_cursor_move_ms: int = 220,
    ) -> None:
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.channel = channel
        self.user_data_dir = Path(user_data_dir).resolve()
        self.search_engine = search_engine
        self.image_search_engine = image_search_engine
        self.cdp_url = cdp_url
        self.agent_cursor_enabled = agent_cursor_enabled
        self.agent_cursor_label = agent_cursor_label
        self.agent_cursor_move_ms = agent_cursor_move_ms
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._browser = None
        self._page: Page | None = None
        self._owns_context = False
        self._lock = asyncio.Lock()
        # Shared with semantic DOM operations; never launch a second browser.
        self.operator_lock = asyncio.Lock()
        self._operator_epoch = 0
        self._tab_ids: dict[Page, str] = {}
        self._observed_pages: set[Page] = set()
        self._operator_dom = None
        self._observed_context = None
        self._session_id: str | None = None
        self._operator_pinned_page: Page | None = None

    @property
    def session_id(self) -> str | None:
        self._observe_context()
        return self._session_id

    def _observe_context(self) -> None:
        if self._context is self._observed_context:
            return
        self.invalidate_operator_snapshot()
        self._observed_context = self._context
        self._operator_pinned_page = None
        self._session_id = f"browser-{uuid4().hex}" if self._context is not None else None
        if self._context is not None:
            observed = self._context

            def new_page(page: Page) -> None:
                if self._context is observed:
                    self.tab_id(page)
                    self._page = page
                    self.invalidate_operator_snapshot()

            observed.on("page", new_page)

    def invalidate_operator_snapshot(self) -> None:
        self._operator_epoch += 1

    def tab_id(self, page: Page) -> str:
        if page not in self._tab_ids:
            self._tab_ids[page] = f"tab-{uuid4().hex}"
        if page not in self._observed_pages:
            self._observed_pages.add(page)
            page.on("close", lambda *_: self.invalidate_operator_snapshot())
            page.on("framenavigated", lambda *_: self.invalidate_operator_snapshot())
        return self._tab_ids[page]

    def release_operator_page_pin(self) -> None:
        self._operator_pinned_page = None

    @property
    def operator_dom(self):
        if self._operator_dom is None:
            from uni.operator.dom import DOMOperator

            self._operator_dom = DOMOperator(self)
        return self._operator_dom

    async def start(self) -> None:
        if self._context is not None:
            return
        async with self._lock:
            if self._context is not None:
                return
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = await async_playwright().start()
            if self.cdp_url:
                # Attach to an already-running Chrome (e.g. with --remote-debugging-port=9222).
                # This keeps the user's connected devices/sessions alive.
                try:
                    self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
                    if not self._browser.contexts:
                        raise RuntimeError("cdp_existing_context_unavailable")
                    self._context = self._browser.contexts[0]
                    self._owns_context = False
                    pages = self._context.pages
                    self._page = pages[0] if pages else None
                    self._observe_context()
                    await self._install_agent_cursor()
                    return
                except Exception as exc:
                    # P0 (owner directive 2026-09-12): CDP attach failure must NOT
                    # abort the task when a managed browser can still be launched.
                    # Fall back to a normal persistent-context launch below. Keep
                    # the playwright instance alive: it is reused for the launch.
                    self._browser = None
                    self._context = None
                    self._observe_context()
            launch_options: dict[str, Any] = {
                "headless": self.headless,
                "viewport": self.viewport,
            }
            if self.channel:
                launch_options["channel"] = self.channel
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self.user_data_dir), **launch_options
                )
                self._owns_context = True
            except Exception:
                launch_options.pop("channel", None)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self.user_data_dir), **launch_options
                )
                self._owns_context = True
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            self._observe_context()
            await self._install_agent_cursor()

    async def _install_agent_cursor(self) -> None:
        if not self.agent_cursor_enabled or self.headless or self._context is None:
            return
        try:
            from uni.agent_cursor import install_on_context

            await install_on_context(self._context)
        except Exception:
            pass

    async def close(self) -> None:
        self.invalidate_operator_snapshot()
        context, playwright = self._context, self._playwright
        self._context = None
        self._observe_context()
        self._playwright = None
        self._page = None
        owns_context = self._owns_context
        self._owns_context = False
        self._browser = None
        if context is not None and owns_context:
            await context.close()
        if playwright is not None:
            await playwright.stop()

    async def ensure_alive(self) -> None:
        """Re-create the browser context if it was closed by a crash/timeout."""
        disconnected = self._browser is not None and not self._browser.is_connected()
        inaccessible = False
        if self._context is not None and not disconnected:
            try:
                self._context.pages
            except Exception:
                inaccessible = True
        if self._context is None or disconnected or inaccessible:
            if self._context is not None:
                try:
                    if self._owns_context:
                        await self._context.close()
                except Exception:
                    pass
                self._context = None
                self._page = None
                self._owns_context = False
                self._browser = None
            await self.start()

    async def active_page(self, *, start_if_missing: bool = True) -> Page | None:
        """Return the tracked page; inspection must use start_if_missing=False.

        The read-only branch does not start/attach a runtime or create a page.
        It notices focus changes among pages already in this session.
        """
        if start_if_missing:
            await self.ensure_alive()
        self._observe_context()
        if self._context is None or (self._browser is not None and not self._browser.is_connected()):
            return None
        try:
            pages = [page for page in self._context.pages if not page.is_closed()]
        except Exception:
            if not start_if_missing:
                return None
            raise
        for candidate in pages:
            self.tab_id(candidate)
        pinned = self._operator_pinned_page
        if pinned is not None and pinned in pages and not pinned.is_closed():
            self._page = pinned
        elif not start_if_missing:
            focused = []
            for candidate in pages:
                try:
                    if await candidate.evaluate("() => document.hasFocus()"):
                        focused.append(candidate)
                except Exception:
                    continue
            if len(focused) == 1 and self._page is not focused[0]:
                self.invalidate_operator_snapshot()
                self._page = focused[0]
        if self._page is None or self._page.is_closed():
            self.invalidate_operator_snapshot()
            self._page = pages[-1] if pages else (await self._context.new_page() if start_if_missing else None)
        if self._page is not None:
            self.tab_id(self._page)
        return self._page

    async def list_tabs(self) -> list[dict[str, Any]]:
        active = await self.active_page(start_if_missing=False)
        if self._context is None:
            return []
        tabs = []
        for page in self._context.pages:
            if not page.is_closed():
                tabs.append({"tab_id": self.tab_id(page), "url": page.url,
                             "title": await page.title(), "active": page is active})
        return tabs

    async def change_tab(self, action: str, *, tab_id: str = "", url: str = "") -> dict[str, Any]:
        async with self.operator_lock:
            self.invalidate_operator_snapshot()
            if action == "new_tab":
                await self.ensure_alive()
                assert self._context is not None
                page = await self._context.new_page()
                self._page = page
                if url:
                    await page.goto(self._sanitize_url(url), wait_until="domcontentloaded", timeout=30_000)
            else:
                if self._context is None:
                    raise RuntimeError("browser_not_running")
                page = next((p for p in self._context.pages
                             if not p.is_closed() and self.tab_id(p) == tab_id), None)
                if page is None:
                    raise ValueError("unknown_tab")
                if action == "close_tab":
                    await page.close()
                    if self._page is page:
                        self._page = None
                    if self._operator_pinned_page is page:
                        self._operator_pinned_page = None
                    return {"closed_tab_id": tab_id}
                if action != "switch_tab":
                    raise ValueError("unsupported_tab_action")
                self._page = page
            await page.bring_to_front()
            self._operator_pinned_page = page
            return {"tab_id": self.tab_id(page), "url": page.url, "title": await page.title()}

    async def history(self, *, forward: bool = False) -> dict[str, Any]:
        async with self.operator_lock:
            page = await self.active_page(start_if_missing=False)
            if page is None:
                raise RuntimeError("browser_not_running")
            self.invalidate_operator_snapshot()
            if forward:
                await page.go_forward(wait_until="domcontentloaded", timeout=30_000)
            else:
                await page.go_back(wait_until="domcontentloaded", timeout=30_000)
            return {"tab_id": self.tab_id(page), "url": page.url, "title": await page.title()}

    async def page_for_host(self, host: str, *, create_url: str | None = None) -> Page:
        self.invalidate_operator_snapshot()
        await self.ensure_alive()
        assert self._context is not None
        host = host.lower()
        for page in reversed(self._context.pages):
            if not page.is_closed() and host in urlparse(page.url).netloc.lower():
                self._page = page
                await page.bring_to_front()
                return page
        page = await self._context.new_page()
        self._page = page
        if create_url:
            await page.goto(create_url, wait_until="domcontentloaded", timeout=30_000)
        await page.bring_to_front()
        return page

    @staticmethod
    def _sanitize_url(raw: str) -> str:
        """Strip voice/STT artifacts like `@url:` wrappers, backticks, stray spaces."""
        url = raw.strip().strip("`").strip()
        # strip a leading `@url:` (or `url:`) wrapper sometimes emitted by STT/LLM
        m = re.match(r"^(?:@?url\s*:\s*)?(.+)$", url, flags=re.IGNORECASE)
        if m:
            url = m.group(1).strip().strip("`").strip()
        if not urlparse(url).scheme:
            url = f"https://{url}"
        return url

    async def navigate(self, url: str) -> Page:
        async with self.operator_lock:
            self.invalidate_operator_snapshot()
            url = self._sanitize_url(url)
            page = await self.active_page()
            assert page is not None
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.bring_to_front()
            return page

    async def search_web(self, query: str) -> tuple[Page, list[dict[str, str]]]:
        url = self.search_engine.format(query=quote_plus(query))
        page = await self.navigate(url)
        try:
            await page.wait_for_selector("li.b_algo h2 a", timeout=8_000)
        except Exception:
            pass
        results = await page.locator("li.b_algo h2 a").evaluate_all(
            """links => links.slice(0, 8).map(a => ({
                title: (a.textContent || '').trim(),
                url: a.href || ''
            })).filter(item => item.title && item.url)"""
        )
        if not results:
            results = await page.locator("a[href^='http']").evaluate_all(
                """links => links.slice(0, 20).map(a => ({
                    title: (a.textContent || '').trim(),
                    url: a.href || ''
                })).filter(item => item.title && item.url)"""
            )
        return page, results[:8]

    async def search_images(self, query: str) -> tuple[Page, list[dict[str, str]]]:
        url = self.image_search_engine.format(query=quote_plus(query))
        page = await self.navigate(url)
        decline = page.get_by_text("Нет, спасибо", exact=True)
        try:
            if await decline.count() == 1:
                await decline.click(timeout=2_000)
        except Exception:
            pass
        try:
            await page.wait_for_selector("img", timeout=8_000)
        except Exception:
            pass
        if "yandex." in urlparse(page.url).netloc.lower():
            results = await page.locator("img").evaluate_all(
                """images => images.map(image => {
                    const link = image.closest('a[href]');
                    return {
                        title: (image.alt || '').trim().slice(0, 300),
                        image_url: image.currentSrc || image.src || '',
                        source_url: link?.href || ''
                    };
                }).filter(item => item.image_url && item.image_url.startsWith('http')).slice(0, 12)"""
            )
        else:
            results = await page.locator("a.iusc").evaluate_all(
                """links => links.slice(0, 12).map(a => {
                    try {
                        const item = JSON.parse(a.getAttribute('m') || '{}');
                        return {title: item.t || '', image_url: item.murl || '', source_url: item.purl || ''};
                    } catch (_) { return null; }
                }).filter(item => item && item.image_url)"""
            )
        return page, results[:12]

    async def click_locator(self, locator, *, timeout: float = 10_000) -> None:
        """DOM click with optional visible UNI cursor (OS mouse not moved)."""
        self.invalidate_operator_snapshot()
        page = await self.active_page()
        if self.agent_cursor_enabled and not self.headless:
            from uni.agent_cursor import click_with_cursor

            await click_with_cursor(
                page,
                locator,
                label=self.agent_cursor_label,
                move_ms=self.agent_cursor_move_ms,
                timeout=timeout,
            )
        else:
            await locator.click(timeout=timeout)

    async def fill_locator(self, locator, text: str, *, timeout: float = 10_000) -> None:
        """Focus + fill with optional UNI cursor overlay."""
        self.invalidate_operator_snapshot()
        page = await self.active_page()
        if self.agent_cursor_enabled and not self.headless:
            from uni.agent_cursor import fill_with_cursor

            await fill_with_cursor(
                page,
                locator,
                text,
                label=self.agent_cursor_label,
                move_ms=self.agent_cursor_move_ms,
                timeout=timeout,
            )
        else:
            await locator.click(timeout=timeout)
            await locator.fill(text, timeout=timeout)
