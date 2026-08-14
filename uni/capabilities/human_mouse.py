"""Человеко-подобная мышь (win32api) — восстановленный модуль.

Отсутствовал на диске (импортировался из computer.py и routers_desktop.py,
из-за чего click_human/double_click_human/drag_human и кнопка «Демо мыши»
падали или тихо откатывались на pyautogui). Движение — кривая Безье со
смещёнными контрольными точками + минимально-рывковый профиль скорости
(10t^3 - 15t^4 + 6t^5), это и есть «человеко-подобная» траектория из
директивы. Клик подсвечивается лайм-кольцом UniActionBadge («мышь Юни»).

Безопасно импортировать без дисплея/win32 — конструктор бейджа сам уходит в
no-op (см. uni/action_badge.py); падения самого win32api (нет курсора/сессии)
пробрасываются наверх — вызывающий код (ComputerCapability) уже откатывается
на pyautogui при ошибке инициализации.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

import win32api

from uni.action_badge import UniActionBadge

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

_BUTTON_EVENTS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


@dataclass
class HumanMouseSettings:
    move_duration: float = 0.35   # секунд на перемещение (клампится 0.05..2.0)
    steps_per_second: int = 60    # частота промежуточных точек траектории
    curve_jitter: float = 0.15    # случайное отклонение кривой (доля от расстояния)
    show_badge: bool = True       # лайм-кольцо «Юни» на клике
    badge_label: str = "Юни"
    click_delay: float = 0.06     # пауза между down/up при клике


class HumanMouseController:
    """Двигает системный курсор по кривой Безье с плавным (не линейным) ускорением."""

    def __init__(self, settings: HumanMouseSettings | None = None) -> None:
        self.settings = settings or HumanMouseSettings()
        self._badge: UniActionBadge | None = None
        if self.settings.show_badge:
            try:
                self._badge = UniActionBadge(enabled=True, label=self.settings.badge_label)
            except Exception:
                self._badge = None
        # 🤖 Hermes (2026-08-14): safety-гейт — Юни НЕ должна лишать пользователя
        # управления мышью. Если пользователь трогает мышь/клавиатуру во время
        # движения Юни, движение прерывается (уступка физическому вводу).
        self._aborted = False
        self._last_our_pos: tuple[int, int] | None = None

    def _flash(self, x: int, y: int, action: str) -> None:
        if self._badge is not None:
            try:
                self._badge.flash_at(x, y, action)
            except Exception:
                pass

    @staticmethod
    def _ease(t: float) -> float:
        # минимально-рывковый профиль скорости (minimum-jerk)
        return 10 * t**3 - 15 * t**4 + 6 * t**5

    def _bezier_path(self, x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int]]:
        duration = max(0.05, min(self.settings.move_duration, 2.0))
        steps = max(2, int(duration * self.settings.steps_per_second))
        dx, dy = (x2 - x1), (y2 - y1)
        dist = (dx * dx + dy * dy) ** 0.5
        jitter = self.settings.curve_jitter * dist
        nx, ny = -dy, dx
        norm = (nx * nx + ny * ny) ** 0.5 or 1.0
        nx, ny = nx / norm, ny / norm
        off1 = random.uniform(-jitter, jitter)
        off2 = random.uniform(-jitter, jitter)
        c1 = (x1 + dx * 0.33 + nx * off1, y1 + dy * 0.33 + ny * off1)
        c2 = (x1 + dx * 0.66 + nx * off2, y1 + dy * 0.66 + ny * off2)
        points: list[tuple[int, int]] = []
        for i in range(steps + 1):
            t = self._ease(i / steps)
            mt = 1 - t
            x = (mt**3) * x1 + 3 * (mt**2) * t * c1[0] + 3 * mt * (t**2) * c2[0] + (t**3) * x2
            y = (mt**3) * y1 + 3 * (mt**2) * t * c1[1] + 3 * mt * (t**2) * c2[1] + (t**3) * y2
            points.append((int(round(x)), int(round(y))))
        return points

    async def move_to(self, x: int, y: int) -> None:
        x0, y0 = win32api.GetCursorPos()
        self._last_our_pos = (x0, y0)
        path = self._bezier_path(x0, y0, int(x), int(y))
        delay = max(0.001, self.settings.move_duration / max(1, len(path)))
        for px, py in path:
            # 🤖 Hermes (2026-08-14): уступка физическому вводу — если
            # пользователь дёрнул мышь или нажал клавишу, Юни останавливается.
            if self._aborted or self._user_took_over():
                return
            win32api.SetCursorPos((px, py))
            self._last_our_pos = (px, py)
            await asyncio.sleep(delay)
        if not (self._aborted or self._user_took_over()):
            win32api.SetCursorPos((int(x), int(y)))
            self._last_our_pos = (int(x), int(y))

    def abort(self) -> None:
        """Немедленно остановить любое текущее/следующее движение Юни."""
        self._aborted = True

    def _user_took_over(self) -> bool:
        """True, если пользователь перехватил управление во время движения Юни."""
        try:
            cx, cy = win32api.GetCursorPos()
            if self._last_our_pos is not None:
                # курсор сместился не на последнюю нашу точку -> пользователь двигает
                if (cx, cy) != self._last_our_pos:
                    return True
            # любая клавиша/кнопка мыши нажата -> пользователь активен
            for vk in (0x01, 0x02, 0x10, 0x11, 0x12):  # LMB, RMB, SHIFT, CTRL, ALT
                if win32api.GetAsyncKeyState(vk) & 0x8000:
                    return True
        except Exception:
            pass
        return False

    async def click(self, x: int, y: int, button: str = "left") -> None:
        await self.move_to(x, y)
        down, up = _BUTTON_EVENTS.get(button, _BUTTON_EVENTS["left"])
        win32api.mouse_event(down, 0, 0, 0, 0)
        await asyncio.sleep(self.settings.click_delay)
        win32api.mouse_event(up, 0, 0, 0, 0)
        self._flash(int(x), int(y), f"click:{button}")

    async def double_click(self, x: int, y: int, button: str = "left") -> None:
        await self.click(x, y, button)
        await asyncio.sleep(self.settings.click_delay * 2)
        down, up = _BUTTON_EVENTS.get(button, _BUTTON_EVENTS["left"])
        win32api.mouse_event(down, 0, 0, 0, 0)
        await asyncio.sleep(self.settings.click_delay)
        win32api.mouse_event(up, 0, 0, 0, 0)
        self._flash(int(x), int(y), f"double_click:{button}")

    async def drag(self, x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
        await self.move_to(x1, y1)
        down, up = _BUTTON_EVENTS.get(button, _BUTTON_EVENTS["left"])
        win32api.mouse_event(down, 0, 0, 0, 0)
        await asyncio.sleep(self.settings.click_delay)
        await self.move_to(x2, y2)
        win32api.mouse_event(up, 0, 0, 0, 0)
        self._flash(int(x2), int(y2), f"drag:{button}")

    def close(self) -> None:
        if self._badge is not None:
            try:
                self._badge.close()
            except Exception:
                pass
