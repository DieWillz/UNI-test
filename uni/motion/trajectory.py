"""Генерация плавных траекторий для курсора.

Чистые функции без побочных эффектов и без GUI/pyautogui — легко
тестировать в headless-среде. Адаптировано из ТЗ «MVP xtoys browser mouse»,
сохранена обратная совместимость API (build_move_path / build_wander_path /
build_circle_path / MousePath / clamp / ease_in_out_cubic).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]  # x, y, width, height


def clamp(value: float, lo: float, hi: float) -> float:
    """Загнать значение в [lo, hi]."""
    return max(lo, min(hi, value))


def ease_in_out_cubic(t: float) -> float:
    """Плавный разгон и торможение (Fitts's Law-подобно)."""
    t = clamp(t, 0.0, 1.0)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


@dataclass(frozen=True, slots=True)
class MousePath:
    """Траектория: точки + паузы (сек) после каждой точки."""

    points: tuple[Point, ...]
    delays: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.points) != len(self.delays):
            raise ValueError("points и delays должны быть одной длины")

    @property
    def duration(self) -> float:
        return sum(self.delays)


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    """Кубическая кривая Безье через контрольные точки."""
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def build_move_path(
    start: Point,
    end: Point,
    duration: float = 1.0,
    *,
    fps: int = 90,
    humanize: bool = True,
    rng: random.Random | None = None,
) -> MousePath:
    """Путь start → end: кубическая Безье + easing + микро-шум «живой руки»."""
    rng = rng or random.Random()
    dx, dy = end[0] - start[0], end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance < 1.0 or duration <= 0.0:
        return MousePath(points=(end,), delays=(max(duration, 0.02),))

    steps = int(clamp(duration * fps, 8.0, 360.0))
    # Контрольные точки у 1/3 и 2/3 отрезка, смещены по нормали.
    nx, ny = -dy / distance, dx / distance
    spread = distance * (rng.uniform(0.08, 0.22) if humanize else 0.04)
    side = rng.choice((-1.0, 1.0)) if humanize else 1.0

    def jitter() -> float:
        return rng.uniform(-4.0, 4.0) if humanize else 0.0

    c1 = (
        start[0] + dx / 3.0 + nx * spread * side + jitter(),
        start[1] + dy / 3.0 + ny * spread * side + jitter(),
    )
    c2 = (
        start[0] + 2.0 * dx / 3.0 + nx * spread * side * 0.6 + jitter(),
        start[1] + 2.0 * dy / 3.0 + ny * spread * side * 0.6 + jitter(),
    )

    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(1, steps + 1):
        points.append(_bezier(start, c1, c2, end, ease_in_out_cubic(i / steps)))
        delays.append(base_delay * (rng.uniform(0.7, 1.3) if humanize else 1.0))
    points[-1] = end  # финишируем ровно в цели
    return MousePath(points=tuple(points), delays=tuple(delays))


def build_wander_path(
    bounds: Bounds,
    duration: float = 12.0,
    *,
    fps: int = 90,
    rng: random.Random | None = None,
) -> MousePath:
    """Плавное «гуляние» внутри bounds: кривая Лиссажу со случайными параметрами."""
    rng = rng or random.Random()
    x0, y0, w, h = bounds
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    ax, ay = w * 0.42, h * 0.42
    a, b = rng.choice((1, 2, 3)), rng.choice((1, 2, 3))
    if a == b:  # не даём выродиться в эллипс
        b = a + 1
    phase = rng.uniform(0.0, math.tau)

    steps = int(clamp(duration * fps, 16.0, 4000.0))
    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(steps):
        t = math.tau * i / (steps - 1)
        points.append((cx + ax * math.sin(a * t + phase), cy + ay * math.sin(b * t)))
        delays.append(base_delay * rng.uniform(0.85, 1.15))
    return MousePath(points=tuple(points), delays=tuple(delays))


def build_circle_path(
    center: Point,
    radius: float,
    *,
    turns: float = 1.0,
    duration: float = 6.0,
    fps: int = 90,
    start_angle: float = -math.pi / 2.0,
) -> MousePath:
    """Круг/спираль вокруг center."""
    steps = int(clamp(duration * fps, 16.0, 4000.0))
    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(steps + 1):
        angle = start_angle + math.tau * turns * i / steps
        points.append(
            (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
        )
        delays.append(base_delay)
    return MousePath(points=tuple(points), delays=tuple(delays))
