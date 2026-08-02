from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

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
    ) -> None:
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.channel = channel
        self.user_data_dir = Path(user_data_dir).resolve()
        self.search_engine = search_engine
        self.image_search_engine = image_search_engine
        self.cdp_url = cdp_url
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._browser = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

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
                    self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
                    pages = self._context.pages
                    self._page = pages[0] if pages else await self._context.new_page()
                    return
                except Exception as exc:
                    console = __import__("rich.console", fromlist=["Console"]).Console()
                    console.print(f"[yellow]Не удалось подключиться к CDP {self.cdp_url}: {exc}. Запускаю свой браузер.[/yellow]")
                    self._browser = None
                    self._context = None
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
            except Exception:
                launch_options.pop("channel", None)
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(self.user_data_dir), **launch_options
                )
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()

    async def close(self) -> None:
        context, playwright = self._context, self._playwright
        self._context = None
        self._playwright = None
        self._page = None
        if context is not None:
            await context.close()
        if playwright is not None:
            await playwright.stop()

    async def ensure_alive(self) -> None:
        """Re-create the browser context if it was closed by a crash/timeout."""
        if self._context is None or getattr(self._context, "closed", False) or self._context._close_was_called:
            if self._context is not None:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None
                self._page = None
            await self.start()

    async def active_page(self) -> Page:
        await self.ensure_alive()
        assert self._context is not None
        if self._page is None or self._page.is_closed():
            pages = [page for page in self._context.pages if not page.is_closed()]
            self._page = pages[-1] if pages else await self._context.new_page()
        return self._page

    async def page_for_host(self, host: str, *, create_url: str | None = None) -> Page:
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
        url = self._sanitize_url(url)
        page = await self.active_page()
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
