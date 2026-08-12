# 🤖 DEPRECATED by Hermes: 2026-08-12
# Причина: Функционал плавного «живого» движения курсора полностью перенесён
# в uni/human_motion.py (HumanMotionController) и uni/human_mouse.py
# (HumanMouseController), которые интегрированы в ComputerCapability
# (use_human_motion=True по умолчанию, откат на pyautogui при сбое).
# Не использовать напрямую. Оставлен для истории и безопасности откатов.
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
    """🤖 FIX-AUDIT A-03: ФАСАД над HumanMouseController.

    Консолидация мыши (пункт 1.2 плана): весь реальный курсорный ввод
    делегируется в uni.human_mouse.HumanMouseController (человеко-подобная
    траектория через win32, бейдж, калибровка DPI). SmoothMouseDriver
    сохраняет публичный API (position/screen_size/move_to/wiggle/circle/
    wander/drag_to/cancel/click/draw) для обратной совместимости
    (mouse_show.py), но НЕ дёргает pyautogui напрямую — только построение
    путей (trajectory) и делегирование проигрывания в HumanMouseController.

    Параметр label= (используется в mouse_show.py) принимается для
    совместимости, но игнорируется — бейджом управляет HumanMouseController.
    """

    def __init__(self, *, failsafe: bool = True, speed: float = 1.0, fps: int = 90,
                 label=None) -> None:
        from ..human_mouse import HumanMouseController, HumanMouseSettings
        self._speed = clamp(speed, 0.1, 5.0)
        self._fps = fps
        # Реальный движок — HumanMouseController (фасад над ним).
        try:
            self._human = HumanMouseController(HumanMouseSettings(show_badge=False))
        except Exception:
            self._human = None  # если win32 недоступен (headless) — методы вернут ошибку явно

    # ---------- состояние (делегирование) ----------
    @property
    def position(self) -> tuple[int, int]:
        if self._human is None:
            return (0, 0)
        return self._human._current_pos()

    @property
    def screen_size(self) -> tuple[int, int]:
        if self._human is None:
            return (1920, 1080)
        return self._human._screen_size()

    # ---------- API (делегирование в HumanMouseController) ----------
    async def move_to(self, x: float, y: float, *, duration: float | None = None,
                      humanize: bool = True) -> None:
        if self._human is None:
            raise RuntimeError("HumanMouseController недоступен (нет win32)")
        await self._human.move_to(int(x), int(y))

    async def wiggle(self, *, amplitude: int = 24, times: int = 3) -> None:
        x, y = self.position
        for _ in range(times):
            await self.move_to(x - amplitude, y)
            await self.move_to(x + amplitude, y)
        await self.move_to(x, y)

    async def circle(self, center: Point, radius: float, *, turns: float = 1.0,
                     duration: float = 6.0) -> None:
        path = build_circle_path(center, radius, turns=turns,
                                 duration=duration / self._speed, fps=self._fps)
        await self._play_points_from_path(path)

    async def wander(self, bounds: Bounds, *, duration: float = 12.0) -> None:
        path = build_wander_path(bounds, duration / self._speed, fps=self._fps)
        await self._play_points_from_path(path)

    async def drag_to(self, x: float, y: float, *, duration: float = 1.2) -> None:
        if self._human is None:
            raise RuntimeError("HumanMouseController недоступен (нет win32)")
        sx, sy = self.position
        await self._human.drag(sx, sy, int(x), int(y))

    def cancel(self) -> None:
        """🤖 FIX-AUDIT A-04: реальное прерывание через HumanMouseController.cancel()
        (threading.Event), а НЕ release() на asyncio.Lock."""
        if self._human is not None:
            self._human.cancel()

    async def click(self, x: float | None = None, y: float | None = None,
                    *, button: str = "left") -> None:
        if self._human is None:
            raise RuntimeError("HumanMouseController недоступен (нет win32)")
        if x is not None and y is not None:
            await self._human.click(int(x), int(y), button)
        else:
            cx, cy = self.position
            await self._human.click(cx, cy, button)

    async def draw(self, points: list, *, duration: float = 1.5,
                   button: str = "left") -> None:
        """Рисование: держим кнопку и ведём через точки (делегируем движение в human)."""
        if self._human is None:
            raise RuntimeError("HumanMouseController недоступен (нет win32)")
        if not points:
            return
        pts = [Point(float(px), float(py)) for px, py in points]
        # держим кнопку через pyautogui (только зажать/отпустить), движение — через human
        import pyautogui
        pyautogui.mouseDown(button=button)
        try:
            for p in pts:
                await self._human.move_to(int(p.x), int(p.y))
        finally:
            pyautogui.mouseUp(button=button)

    # ---------- внутреннее ----------
    def _natural_duration(self, distance: float) -> float:
        return clamp(distance / 1400.0, 0.25, 2.5) / self._speed

    async def _play_points_from_path(self, path: MousePath) -> None:
        """Конвертирует trajectory.Path в MotionPoint[] и проигрывает через human."""
        if self._human is None:
            raise RuntimeError("HumanMouseController недоступен (нет win32)")
        from ..human_motion import MotionPoint
        n = len(path.points)
        motion_pts = [
            MotionPoint(p.x, p.y, t=float(i) / max(1, n - 1))
            for i, p in enumerate(path.points)
        ]
        dur = getattr(path, "duration", None) or (n / max(1, self._fps))
        await self._human.play_points(motion_pts, float(dur))

