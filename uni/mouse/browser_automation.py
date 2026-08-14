"""Автоматизация браузера через мышь Юни (поверх существующего HumanMouseController).

Hermes, 2026-08-14. Не создаём второй HumanMouseController — импортируем уже
существующий uni.capabilities.human_mouse.HumanMouseController (async API:
move_to/click/double_click/drag). Добавляем поверх: поиск иконок (IconFinder,
внешний Moondream) + визуальную подсветку (VisualFeedback) + оконные хелперы
через win32 (не дублируем логику движения мыши).
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Tuple

from uni.mouse.icon_finder import IconFinder, IconMatch
from uni.mouse.visual_feedback import VisualFeedback

try:
    import win32gui
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


class BrowserAutomation:
    """Открытие браузера/вкладок/URL через визуально подсвечиваемые клики мыши."""

    def __init__(self) -> None:
        self.vision = IconFinder()
        self.feedback = VisualFeedback()

    # ---- window helpers (win32, не дублирует движение мыши) ----------------
    def find_window(self, title_fragment: str) -> Optional[int]:
        if not _HAS_WIN32:
            return None
        result: list[int] = []

        def cb(hwnd, _):
            if title_fragment.lower() in win32gui.GetWindowText(hwnd).lower():
                result.append(hwnd)
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            return None
        return result[0] if result else None

    def bring_to_front(self, hwnd: int) -> bool:
        if not _HAS_WIN32:
            return False
        try:
            win32gui.ShowWindow(hwnd, 5)  # SW_RESTORE
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def get_window_region(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        if not _HAS_WIN32:
            return None
        try:
            r = win32gui.GetWindowRect(hwnd)
            return (r[0], r[1], r[2] - r[0], r[3] - r[1])
        except Exception:
            return None

    # ---- human mouse (существующий контроллер) -----------------------------
    async def _mouse(self):
        # Ленивый импорт, чтобы не тянуть win32 при import пакета.
        from uni.capabilities.human_mouse import HumanMouseController
        return HumanMouseController()

    async def _click_icon(self, match: IconMatch, double: bool = False) -> bool:
        mouse = await self._mouse()
        self.feedback.highlight_region(
            (match.region[0] - 10, match.region[1] - 10,
             match.region[2] + 20, match.region[3] + 20),
            (0, 255, 0), duration=1.0,
        )
        await mouse.move_to(match.position[0], match.position[1])
        if double:
            await mouse.double_click(match.position[0], match.position[1])
        else:
            await mouse.click(match.position[0], match.position[1])
        return True

    # ---- public flows --------------------------------------------------------
    async def open_browser(self, browser_name: str = "Яндекс") -> Optional[int]:
        for desc in (f"иконка {browser_name} Браузера", browser_name, f"{browser_name} Browser"):
            m = self.vision.find_icon(desc)
            if m:
                await self._click_icon(m, double=True)
                time.sleep(3)
                return self.find_window(browser_name)
        return None

    async def open_new_tab(self, browser_hwnd: Optional[int] = None) -> bool:
        hwnd = browser_hwnd or self.find_window("Браузер") or self.find_window("Yandex")
        if hwnd is None:
            return False
        self.bring_to_front(hwnd)
        region = self.get_window_region(hwnd)
        m = self.vision.find_icon("кнопка новая вкладка", region=region)
        if not m:
            # fallback: фиксированная позиция (правый верх угол обычно)
            if region:
                x, y, w, h = region
                m = IconMatch(position=(x + w - 60, y + 35), region=(x + w - 80, y + 20, 40, 30),
                              confidence=0.4, description="new tab fallback")
        if not m:
            return False
        await self._click_icon(m)
        time.sleep(1)
        return True

    async def type_url(self, url: str, browser_hwnd: Optional[int] = None) -> bool:
        hwnd = browser_hwnd or self.find_window("Браузер") or self.find_window("Yandex")
        if hwnd is None:
            return False
        self.bring_to_front(hwnd)
        region = self.get_window_region(hwnd)
        m = self.vision.find_icon("адресная строка", region=region)
        if not m:
            if region:
                x, y, w, h = region
                m = IconMatch(position=(x + w // 2, y + 50), region=(x + w // 2 - 200, y + 35, 400, 30),
                              confidence=0.4, description="url bar fallback")
        if not m:
            return False
        mouse = await self._mouse()
        await self._click_icon(m)
        time.sleep(0.5)
        # ввод через существующий контроллер (apsync-обёртка вокруг клавиатуры)
        try:
            import pyautogui
            pyautogui.write(url, interval=0.02)
            pyautogui.press("enter")
        except Exception:
            return False
        time.sleep(2)
        return True

    async def open_url(self, url: str, browser_name: str = "Яндекс") -> bool:
        hwnd = await self.open_browser(browser_name)
        if hwnd is None:
            return False
        if not await self.open_new_tab(hwnd):
            return False
        return await self.type_url(url, hwnd)
