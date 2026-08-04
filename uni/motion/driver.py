"""SmoothMouseDriver: единый API мыши для агента/инструментов/сценариев.

Фасад поверх человеческой математики движения (uni.human_motion) и win32-исполнителя
(uni.human_mouse). Сохраняет публичный API, который использовали scenarios/xtoys.py
и другие вызыватели: move_to / click / drag_to / wander / circle / draw / wiggle / cancel.

Бейдж «🖱️ Uni» рядом с кликом — через uni.motion.label.CursorLabelOverlay.flash()
(отдельное окно-бейдж не плодим; вспышка текстом таблички).
"""

from __future__ import annotations

import asyncio

import win32api
import win32con

from uni.human_mouse import HumanMouseController, HumanMouseSettings
from uni.human_motion import MotionPoint


class SmoothMouseDriver:
    """Водит системный курсор плавно: minimum-jerk + easing + микро-шум + overshoot.

    Безопасность: при failsafe увод курсора в левый верхний угол прерывает
    работу (pyautogui.FAILSAFE / win32 — см. HumanMouseController).
    """

    def __init__(
        self,
        *,
        label: object | None = None,
        settings: HumanMouseSettings | None = None,
        failsafe: bool = True,
        speed: float = 1.0,
        fps: int = 90,
    ) -> None:
        # HumanMouseController сам рулит pyautogui.FAILSAFE при первом вызове win32api.
        if settings is None:
            settings = HumanMouseSettings(move_duration=0.35 / max(0.1, speed))
        self._ctrl = HumanMouseController(settings)
        self.label = label  # CursorLabelOverlay (или None) — вспышки «клик» вместо окна-бейджа

    # ---------- состояние ----------
    @property
    def position(self) -> tuple[int, int]:
        return win32api.GetCursorPos()

    @property
    def screen_size(self) -> tuple[int, int]:
        return (win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))

    # ---------- API (имена прежние, внутри — человеко-подобное движение) ----------
    async def move_to(
        self,
        x: float,
        y: float,
        *,
        duration: float | None = None,
        humanize: bool = True,
    ) -> bool:
        """Плавно переместить курсор в точку (x, y). Возвращает успех верификации ±5px."""
        if duration is not None:
            self._ctrl.settings.move_duration = duration
        return await self._ctrl.move_to_verified(int(x), int(y), tolerance=5)

    async def click(self, x: float | None = None, y: float | None = None, *, button: str = "left") -> None:
        if x is not None and y is not None:
            await self.move_to(x, y)
        if self.label is not None and hasattr(self.label, "flash"):
            try:
                self.label.flash(f"🖱️ клик·{button}")
            except Exception:
                pass
        cx, cy = self.position
        await self._ctrl.click(cx, cy, button)

    async def wiggle(self, *, amplitude: int = 24, times: int = 3) -> None:
        """Помахать курсором на месте — жест «привет, это я»."""
        x, y = self.position
        for _ in range(times):
            await self._ctrl.move_to(x - amplitude, y)
            await self._ctrl.move_to(x + amplitude, y)
        await self._ctrl.move_to(x, y)

    async def circle(self, center, radius: float, *, turns: float = 1.0, duration: float = 6.0) -> None:
        from uni.human_motion import build_circle_path

        pts = build_circle_path((center[0], center[1]), radius, turns=turns, steps=int(duration * 90))
        await self._ctrl.play_points(pts, duration)

    async def wander(self, bounds, *, duration: float = 12.0) -> None:
        from uni.human_motion import build_wander_path

        pts = build_wander_path(bounds, duration, fps=90)
        await self._ctrl.play_points(pts, duration)

    async def draw(self, points: list[MotionPoint], duration: float) -> None:
        """Проигрывает произвольную последовательность точек (шоу-фигуры)."""
        await self._ctrl.play_points(points, duration)

    async def drag_to(self, x: float, y: float, *, button: str = "left") -> None:
        """Плавный драг из текущей позиции в (x, y) — пригодится для игрушек."""
        sx, sy = self.position
        await self._ctrl.drag(sx, sy, int(x), int(y), button)

    def cancel(self) -> None:
        """Прервать текущее движение (голос «стоп» / новая команда)."""
        self._ctrl.cancel()
