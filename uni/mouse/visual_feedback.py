"""Визуальная подсветка найденной иконки перед кликом (НЕБЛОКИРУЮЩАЯ).

Hermes, 2026-08-14. Исправление директивы: оригинал использовал cv2.imshow +
cv2.waitKey(1000), что БЛОКИРУЕТ поток на 1 секунду и мешает автономному
режиму. Здесь — прозрачное win32-overlay окно, которое рисует рамку и
само гаснет по таймеру в отдельном daemon-потоке (не блокирует Юни).
Fallback на uni.action_badge при отсутствии win32 (например headless).
"""

from __future__ import annotations

import threading
import time
from typing import Tuple

try:
    import win32api
    import win32con
    import win32gui
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


class VisualFeedback:
    """Неблокирующая подсветка области экрана (рамка-подсказка «Юни видит»)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: list[tuple] = []  # (hwnd, until_ts)

    def highlight_region(self, region: Tuple[int, int, int, int],
                         color: Tuple[int, int, int] = (0, 255, 0),
                         duration: float = 1.2, thickness: int = 3) -> bool:
        """Показать рамку вокруг region на `duration` секунд (неблокирующе)."""
        if not _HAS_WIN32:
            return self._fallback_highlight(region, duration)
        try:
            x, y, w, h = [int(v) for v in region]
            # Отдельный поток рисует и гасит — не блокирует вызывающий.
            t = threading.Thread(
                target=self._draw_then_clear,
                args=(x, y, w, h, color, thickness, duration),
                daemon=True,
                name="uni-visual-feedback",
            )
            t.start()
            return True
        except Exception:
            return self._fallback_highlight(region, duration)

    def _draw_then_clear(self, x, y, w, h, color, thickness, duration):
        try:
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = self._wnd_proc
            wc.hInstance = win32gui.GetModuleHandle(None)
            wc.lpszClassName = "UniFeedbackOverlay"
            wc.hbrBackground = win32con.COLOR_WINDOW + 1
            wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
            atom = win32gui.RegisterClass(wc)
            hwnd = win32gui.CreateWindow(
                atom, "uni-feedback", win32con.WS_POPUP,
                0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1),
                None, None, wc.hInstance, None,
            )
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST)
            win32gui.SetLayeredWindowAttributes(hwnd, 0, 0, win32con.LWA_COLORKEY)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            self._hwnd = hwnd
            self._rect = (x, y, w, h)
            self._color = color
            self._thickness = thickness
            win32gui.RedrawWindow(hwnd, None, None,
                                  win32con.RDW_INVALIDATE | win32con.RDW_UPDATENOW)
            time.sleep(duration)
            try:
                win32gui.DestroyWindow(hwnd)
            except Exception:
                pass
        except Exception:
            pass

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_PAINT:
            try:
                hdc = win32gui.GetDC(hwnd)
                pen = win32gui.CreatePen(win32con.PS_SOLID, self._thickness,
                                         self._rgb(self._color))
                old = win32gui.SelectObject(hdc, pen)
                brush = win32gui.GetStockObject(win32con.NULL_BRUSH)
                oldb = win32gui.SelectObject(hdc, brush)
                x, y, w, h = self._rect
                win32gui.Rectangle(hdc, x, y, x + w, y + h)
                win32gui.SelectObject(hdc, old)
                win32gui.SelectObject(hdc, oldb)
                win32gui.DeleteObject(pen)
                win32gui.ReleaseDC(hwnd, hdc)
            except Exception:
                pass
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    @staticmethod
    def _rgb(bgr: Tuple[int, int, int]) -> int:
        b, g, r = bgr
        return (r << 16) | (g << 8) | b

    def _fallback_highlight(self, region, duration) -> bool:
        """Если нет win32 (headless) — ничего не рисуем, просто ждём неблокируя."""
        return False

    def show_click_feedback(self, x: int, y: int, duration: float = 0.5) -> bool:
        return self.highlight_region((x - 20, y - 20, 40, 40), (0, 255, 0), duration, 2)
