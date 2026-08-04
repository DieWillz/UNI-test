"""
uni/capabilities/human_mouse.py

Windows-слой поверх human_motion.py — реально двигает системный курсор по
человеко-подобной траектории через win32api (тот же low-level API, что уже
используется в computer.py), кликает с реалистичной задержкой между
mousedown/mouseup, и подсвечивает точку действия через уже существующий
UniActionBadge (см. uni_action_badge.py) — та самая "визуальная" часть,
о которой напрямую просили: видно, где и что делает Юни, а не скрытые клики.

Это ОТДЕЛЬНЫЙ модуль, не правка computer.py — интеграция в execute()/click()
показана отдельным блоком ниже в комментарии HOW TO INTEGRATE, чтобы ты сам
решил, добавлять ли новое действие "click_human" рядом со старым "click"
(рекомендую так — не ломает обратную совместимость) или заменить click()
полностью.
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass

import win32api
import win32con

from .human_motion import HumanMotionConfig, generate_path, step_delays

try:
    from .action_badge import UniActionBadge
except ImportError:  # badge — опционально, движение мыши работает и без него
    try:
        from .uni_action_badge import UniActionBadge
    except ImportError:
        UniActionBadge = None  # type: ignore


# win32 mouse_event флаги (то же самое, что использует pyautogui внутри, но
# без накладных расходов pyautogui.click(), которая сама заново вызывает moveTo)
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
    move_duration: float = 0.35        # общая длительность перемещения, сек (как mouse_move_duration в computer.py)
    click_dwell_range: tuple[float, float] = (0.045, 0.11)  # пауза между mousedown/mouseup — человек не кликает мгновенно
    pre_click_pause_range: tuple[float, float] = (0.03, 0.09)  # короткая пауза "прицеливания" перед кликом
    show_badge: bool = True
    motion: HumanMotionConfig = None  # если None — используются дефолты HumanMotionConfig

    def __post_init__(self):
        if self.motion is None:
            self.motion = HumanMotionConfig()


class HumanMouseController:
    """Двигает и кликает системной мышью по человеко-подобной траектории.

    Не async сам по себе на уровне win32-вызовов (win32api.SetCursorPos —
    синхронный), поэтому вся работа идёт в отдельном потоке через
    asyncio.to_thread — как уже делает click()/type_text() в computer.py,
    чтобы не блокировать event loop агента.
    """

    def __init__(self, settings: HumanMouseSettings | None = None):
        self.settings = settings or HumanMouseSettings()
        self._badge = None
        # threading.Event (не asyncio.Event!) — cancel() может вызываться из
        # любого потока (голос «стоп» из event-loop, а движение в to_thread).
        self._cancel = threading.Event()
        if self.settings.show_badge and UniActionBadge is not None:
            try:
                self._badge = UniActionBadge()
            except Exception:
                # GUI-бейдж требует дисплея; если недоступен (headless/CI) —
                # просто работаем без визуальной подсветки, не роняем клик.
                self._badge = None

    def cancel(self) -> None:
        """Прервать текущее движение — например, пришла новая голосовая команда.
        Идея из разбора DeepSeek/Hermes, реализована без рекурсии (см. move_to_verified)."""
        self._cancel.set()

    @staticmethod
    def _current_pos() -> tuple[int, int]:
        return win32api.GetCursorPos()

    def _move_sync(self, target: tuple[int, int]) -> None:
        start = self._current_pos()
        distance = ((target[0] - start[0]) ** 2 + (target[1] - start[1]) ** 2) ** 0.5

        # Для очень коротких перемещений (courser уже почти на месте) не стоит
        # тратить полную длительность/кривизну — иначе агент будет заметно
        # "тормозить" на серии близких кликов подряд.
        cfg = self.settings.motion
        if distance < 3:
            win32api.SetCursorPos((int(target[0]), int(target[1])))
            return

        path = generate_path(start, target, cfg)
        duration = self.settings.move_duration * min(1.0, max(0.25, distance / 600))
        delays = step_delays(path, duration)

        for point, delay in zip(path[1:], delays):
            if self._cancel.is_set():
                # Новая команда прервала движение — идея DeepSeek/Hermes,
                # без рекурсии: просто выходим, курсор остаётся там, где был.
                self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
                return
            win32api.SetCursorPos((int(round(point.x)), int(round(point.y))))
            if delay > 0:
                time.sleep(delay)

        # Финальная точка — гарантированно ровно цель (generate_path это уже
        # обеспечивает, но SetCursorPos с int() округлением мог сместить на
        # доли пикселя на предпоследнем шаге; фиксируем явно).
        win32api.SetCursorPos((int(target[0]), int(target[1])))

    async def move_to_verified(self, x: int, y: int, *, tolerance: int = 5,
                                max_corrections: int = 3) -> bool:
        """move_to() + закрытый цикл проверки (идея DeepSeek/Hermes: ±5px,
        до нескольких попыток), но БЕЗ рекурсии — обычный bounded-цикл, чтобы
        не было риска ухода в глубину при систематическом промахе (например,
        из-за DPI-скейлинга или второго монитора со смещёнными координатами)."""
        target = (int(x), int(y))
        await self.move_to(*target)
        for _ in range(max_corrections):
            cx, cy = await asyncio.to_thread(self._current_pos)
            if abs(cx - target[0]) <= tolerance and abs(cy - target[1]) <= tolerance:
                return True
            await asyncio.to_thread(self._move_sync, target)
        cx, cy = await asyncio.to_thread(self._current_pos)
        return abs(cx - target[0]) <= tolerance and abs(cy - target[1]) <= tolerance

    def _click_sync(self, x: int, y: int, button: str) -> None:
        down_evt, up_evt = _BUTTON_EVENTS.get(button, _BUTTON_EVENTS["left"])
        time.sleep(random.uniform(*self.settings.pre_click_pause_range))
        # Курсор уже выставлен SetCursorPos — mouse_event принимает ОТНОСИТЕЛЬНЫЕ
        # dx/dy, поэтому передаём 0,0 (иначе клик телепортирует курсор на x,y px).
        win32api.mouse_event(down_evt, 0, 0, 0, 0)
        time.sleep(random.uniform(*self.settings.click_dwell_range))
        win32api.mouse_event(up_evt, 0, 0, 0, 0)

    async def move_to(self, x: int, y: int) -> None:
        target = (int(x), int(y))
        if self._badge is not None:
            self._badge.flash_at(target[0], target[1], "движение")
        await asyncio.to_thread(self._move_sync, target)

    async def click(self, x: int, y: int, button: str = "left") -> None:
        target = (int(x), int(y))
        if self._badge is not None:
            self._badge.flash_at(target[0], target[1], f"клик·{button}")
        await asyncio.to_thread(self._move_sync, target)
        await asyncio.to_thread(self._click_sync, target[0], target[1], button)

    async def double_click(self, x: int, y: int, button: str = "left",
                            gap_range: tuple[float, float] = (0.06, 0.14)) -> None:
        """Двойной клик — не pyautogui.doubleClick() с фиксированным интервалом,
        а два реальных клика с человеческим разбросом между ними."""
        target = (int(x), int(y))
        if self._badge is not None:
            self._badge.flash_at(target[0], target[1], "двойной клик")
        await asyncio.to_thread(self._move_sync, target)
        await asyncio.to_thread(self._click_sync, target[0], target[1], button)
        await asyncio.sleep(random.uniform(*gap_range))
        await asyncio.to_thread(self._click_sync, target[0], target[1], button)

    async def drag(self, x1: int, y1: int, x2: int, y2: int,
                    button: str = "left") -> None:
        """Зажать кнопку в (x1,y1), провести человеко-подобную траекторию
        до (x2,y2) с зажатой кнопкой, отпустить."""
        start, end = (int(x1), int(y1)), (int(x2), int(y2))
        if self._badge is not None:
            self._badge.flash_at(start[0], start[1], "drag старт")
        await asyncio.to_thread(self._move_sync, start)

        down_evt, up_evt = _BUTTON_EVENTS.get(button, _BUTTON_EVENTS["left"])

        def _drag_sync() -> None:
            # mouse_event принимает ОТНОСИТЕЛЬНЫЕ dx/dy — курсор уже на start
            # через SetCursorPos, поэтому 0,0 (не start[0],start[1]!).
            win32api.mouse_event(down_evt, 0, 0, 0, 0)
            time.sleep(random.uniform(0.05, 0.1))
            if self._cancel.is_set():
                self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
                return
            path = generate_path(start, end, self.settings.motion)
            duration = self.settings.move_duration * 1.4  # drag обычно медленнее обычного движения
            delays = step_delays(path, duration)
            for point, delay in zip(path[1:], delays):
                if self._cancel.is_set():
                    self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
                    return
                win32api.SetCursorPos((int(round(point.x)), int(round(point.y))))
                if delay > 0:
                    time.sleep(delay)
            if self._cancel.is_set():
                self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
                return
            # последняя точка пути уже ровно end — финальный SetCursorPos не нужен
            time.sleep(random.uniform(0.05, 0.1))
            win32api.mouse_event(up_evt, 0, 0, 0, 0)

        if self._badge is not None:
            self._badge.flash_at(end[0], end[1], "drag финиш")
        await asyncio.to_thread(_drag_sync)

    def _cancel_is_set_noop(self) -> None:
        pass

    def close(self) -> None:
        if self._badge is not None:
            self._badge.close()

    def _play_sync(self, points: list[MotionPoint], duration: float) -> None:
        """Проигрывает произвольную последовательность точек (шоу-фигуры:
        spiral/heart/wander/circle) тем же low-level конвейером SetCursorPos.
        Последняя точка не гарантируется ровно целью — для декоративных
        фигур это нормально."""
        self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
        delays = step_delays(points, duration)
        for point, delay in zip(points[1:], delays):
            if self._cancel.is_set():
                self._cancel_is_set_noop()  # стиккий стоп: флаг не сбрасываем
                return
            win32api.SetCursorPos((int(round(point.x)), int(round(point.y))))
            if delay > 0:
                time.sleep(delay)

    async def play_points(self, points: list[MotionPoint], duration: float) -> None:
        await asyncio.to_thread(self._play_sync, points, duration)


# ---------------------------------------------------------------------------
# HOW TO INTEGRATE в существующий uni/capabilities/computer.py
# ---------------------------------------------------------------------------
#
# 1. В начало файла добавить импорт:
#
#     from .human_mouse import HumanMouseController, HumanMouseSettings
#
# 2. В ComputerCapability.__init__ добавить:
#
#     self._human_mouse = HumanMouseController(
#         HumanMouseSettings(move_duration=self.mouse_move_duration)
#     )
#
# 3. Добавить новый метод рядом с существующим click() — НЕ заменяя его,
#    чтобы не сломать код, который уже вызывает action="click":
#
#     async def click_human(self, x: int, y: int, button: str = "left") -> ToolResult:
#         try:
#             await self._human_mouse.click(x, y, button)
#             return ToolResult(success=True, message=f"Клик (человеко-подобный) ({x},{y})")
#         except Exception as e:
#             return ToolResult(success=False, message=f"Ошибка: {e}")
#
#     async def drag_human(self, x1: int, y1: int, x2: int, y2: int,
#                           button: str = "left") -> ToolResult:
#         try:
#             await self._human_mouse.drag(x1, y1, x2, y2, button)
#             return ToolResult(success=True, message=f"Drag ({x1},{y1})->({x2},{y2})")
#         except Exception as e:
#             return ToolResult(success=False, message=f"Ошибка: {e}")
#
# 4. В execute() добавить веткУ (рядом с остальными elif):
#
#     elif action == "click_human":
#         return await self.click_human(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("button", "left"))
#     elif action == "drag_human":
#         return await self.drag_human(
#             kwargs.get("x1", 0), kwargs.get("y1", 0),
#             kwargs.get("x2", 0), kwargs.get("y2", 0),
#             kwargs.get("button", "left"),
#         )
#
# Старый action="click" остаётся как есть (быстрый, без органики — полезен
# для случаев, где скорость важнее правдоподобия). "click_human" — новый,
# отдельный путь. Ничего существующего не переписано.
