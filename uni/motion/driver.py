"""Плавное «живое» управление курсором поверх PyAutoGUI.

Адаптировано из ТЗ «MVP xtoys browser mouse». Отличия от ТЗ (сохраняем
реальный код репозитория):
  * Клики и ввод текста НЕ дублируем — для них сценарий использует
    существующий ComputerCapability (там уже плавный заезд + бейдж «UNI»
    + блокировки). Здесь только движение кривой Безье + failsafe.
  * На конечной точке движения вспыхивает бейдж «UNI» через
    uni.action_badge (как в ComputerCapability), чтобы подпись была
    видна и при «гулянии», а не только на клике.
"""

from __future__ import annotations

import asyncio
import math

import pyautogui

from uni.motion.trajectory import (
    Bounds,
    MousePath,
    Point,
    build_circle_path,
    build_move_path,
    build_wander_path,
    clamp,
)

_MIN_FRAME_DT = 1.0 / 240.0


class SmoothMouseDriver:
    """Водит системный курсор плавно: Безье, easing, человеческий шум.

    Безопасность: при failsafe=True резкий увод курсора в левый верхний угол
    экрана прерывает работу (pyautogui.FailSafeException).
    """

    def __init__(self, *, failsafe: bool = True, speed: float = 1.0, fps: int = 90) -> None:
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0.0  # паузами рулим сами через asyncio
        self._speed = clamp(speed, 0.1, 5.0)
        self._fps = fps
        self._busy = asyncio.Lock()

    # ---------- состояние ----------
    @property
    def position(self) -> tuple[int, int]:
        x, y = pyautogui.position()
        return int(x), int(y)

    @property
    def screen_size(self) -> tuple[int, int]:
        w, h = pyautogui.size()
        return int(w), int(h)

    # ---------- API ----------
    async def move_to(
        self,
        x: float,
        y: float,
        *,
        duration: float | None = None,
        humanize: bool = True,
    ) -> None:
        """Плавно переместить курсор в точку (x, y)."""
        start = self.position
        if duration is None:
            duration = self._natural_duration(math.hypot(x - start[0], y - start[1]))
        path = build_move_path(
            start, (float(x), float(y)), duration, fps=self._fps, humanize=humanize
        )
        await self._play(path)

    async def wiggle(self, *, amplitude: int = 24, times: int = 3) -> None:
        """Помахать курсором на месте — жест «привет, это я»."""
        x, y = self.position
        for _ in range(times):
            await self.move_to(x - amplitude, y, duration=0.12, humanize=False)
            await self.move_to(x + amplitude, y, duration=0.12, humanize=False)
        await self.move_to(x, y, duration=0.12, humanize=False)

    async def circle(
        self,
        center: Point,
        radius: float,
        *,
        turns: float = 1.0,
        duration: float = 6.0,
    ) -> None:
        """Обвести курсором круг."""
        path = build_circle_path(
            center, radius, turns=turns, duration=duration / self._speed, fps=self._fps
        )
        await self._play(path)

    async def wander(self, bounds: Bounds, *, duration: float = 12.0) -> None:
        """Плавно поводить курсором внутри bounds в течение duration секунд."""
        path = build_wander_path(bounds, duration / self._speed, fps=self._fps)
        await self._play(path)

    async def drag_to(self, x: float, y: float, *, duration: float = 1.2) -> None:
        """Плавный драг из текущей позиции в (x, y) — пригодится для игрушек."""
        path = build_move_path(self.position, (float(x), float(y)), duration, fps=self._fps)
        async with self._busy:
            await asyncio.to_thread(pyautogui.mouseDown)
            try:
                await self._play_points(path)
            finally:
                await asyncio.to_thread(pyautogui.mouseUp)

    # ---------- внутреннее ----------
    def _natural_duration(self, distance: float) -> float:
        """«Человеческая» длительность: ~1400 px/с, ограничена [0.25, 2.5] с."""
        return clamp(distance / 1400.0, 0.25, 2.5) / self._speed

    async def _play(self, path: MousePath) -> None:
        async with self._busy:
            await self._play_points(path)

    async def _play_points(self, path: MousePath) -> None:
        for (px, py), delay in zip(path.points, path.delays):
            pyautogui.moveTo(px, py, _pause=False)
            await asyncio.sleep(max(delay / self._speed, _MIN_FRAME_DT))
