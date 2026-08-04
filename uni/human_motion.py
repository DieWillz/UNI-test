"""
uni/capabilities/human_motion.py

Чистая математика "человеческого" движения мыши — без зависимости от Windows API,
чтобы её можно было протестировать где угодно (включая CI на Linux).
Реальный вызов win32api/pyautogui — в human_mouse.py, который использует
только generate_path() отсюда.

Основано на трёх реальных характеристиках движения руки человека (не выдумано
"для красоты" — это стандартные модели из HCI/моторного контроля):

1. Траектория — не прямая линия, а слегка изогнутая дуга. Модель: квадратичная
   кривая Безье с одной случайной контрольной точкой, смещённой перпендикулярно
   отрезку старт->финиш. Амплитуда смещения пропорциональна расстоянию (короткие
   движения — почти прямые, длинные — заметно изогнутые), что соответствует
   реальным записям движения мыши.

2. Профиль скорости — не постоянная скорость и не просто "плавный старт/стоп",
   а minimum-jerk trajectory: s(t) = 10t^3 - 15t^4 + 6t^5, t в [0,1].
   Это стандартная модель в исследованиях моторного контроля человека
   (Flash & Hogan, 1985) — рука разгоняется, идёт с максимальной скоростью
   в середине пути и плавно тормозит, минимизируя рывок (jerk = производная
   ускорения). У pyautogui.moveTo(duration=...) — линейный или простой ease,
   это не то же самое.

3. Микро-дрожание (тремор) — руки человека никогда не двигаются идеально
   гладко. Добавляем случайный шум с амплитудой, убывающей по мере
   приближения к цели (человек "прицеливается" точнее ближе к концу).

4. Overshoot & correction — люди иногда слегка проскакивают мимо цели и
   поправляются коротким обратным движением. Включается с вероятностью
   overshoot_probability.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class MotionPoint:
    x: float
    y: float
    t: float  # 0.0..1.0 доля пройденного времени, для управления скоростью между точками


@dataclass
class HumanMotionConfig:
    steps: int = 40                     # количество промежуточных точек пути
    curve_strength: float = 0.15        # амплитуда изгиба дуги, доля от расстояния (0 = прямая линия)
    jitter_px: float = 1.6              # максимальная амплитуда микро-дрожания в пикселях
    jitter_falloff: float = 2.2         # степень убывания дрожания к концу пути (выше = резче стихает)
    overshoot_probability: float = 0.22 # вероятность промаха с последующей коррекцией
    overshoot_px: tuple[float, float] = (4.0, 14.0)  # диапазон промаха в пикселях
    min_distance_for_curve: float = 12.0  # ниже этого расстояния движение почти прямое
    seed: int | None = None


def _minimum_jerk(t: float) -> float:
    """Стандартный профиль minimum-jerk: s(0)=0, s(1)=1, нулевая скорость
    и ускорение на концах — рука не дёргается в начале/конце движения."""
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _quadratic_bezier(p0: tuple[float, float], p1: tuple[float, float],
                       p2: tuple[float, float], t: float) -> tuple[float, float]:
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
    return x, y


def generate_path(
    start: tuple[float, float],
    end: tuple[float, float],
    cfg: HumanMotionConfig | None = None,
) -> list[MotionPoint]:
    """Строит список точек пути от start до end с человеко-подобной формой
    и профилем скорости. Гарантирует: path[0] == start (t=0), path[-1] == end (t=1).

    Возвращает список MotionPoint — вызывающий код сам решает, с какой реальной
    задержкой между шагами их проигрывать (см. human_mouse.py: пауза между
    шагами вычисляется из общей длительности и производной minimum-jerk,
    чтобы движение реально ускорялось/замедлялось, а не просто состояло из
    точек с равным интервалом).
    """
    cfg = cfg or HumanMotionConfig()
    rng = random.Random(cfg.seed)

    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    distance = math.hypot(dx, dy)

    # Контрольная точка кривой Безье: середина отрезка + смещение перпендикулярно
    # направлению движения. Знак смещения случайный (человек не всегда изгибает
    # движение в одну и ту же сторону).
    if distance < cfg.min_distance_for_curve:
        control = ((x0 + x1) / 2, (y0 + y1) / 2)
    else:
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        # перпендикуляр к вектору (dx, dy), нормированный
        perp_x, perp_y = -dy / distance, dx / distance
        offset = distance * cfg.curve_strength * rng.uniform(0.5, 1.0)
        sign = rng.choice((-1, 1))
        control = (mid_x + perp_x * offset * sign, mid_y + perp_y * offset * sign)

    # Опциональный overshoot: реальная конечная точка чуть дальше цели по
    # направлению движения, потом отдельный короткий сегмент коррекции обратно.
    overshoot_target = None
    if distance >= cfg.min_distance_for_curve and rng.random() < cfg.overshoot_probability:
        overshoot_dist = rng.uniform(*cfg.overshoot_px)
        ux, uy = dx / distance, dy / distance
        overshoot_target = (x1 + ux * overshoot_dist, y1 + uy * overshoot_dist)

    main_target = overshoot_target or (x1, y1)

    path: list[MotionPoint] = []
    # Дрожание масштабируется под расстояние движения: на очень коротких
    # перемещениях (единицы пикселей) полная амплитуда jitter_px доминировала бы
    # над самим движением и выглядела бы как дёрганье, а не как человеческая
    # точность прицеливания. Обнаружено тестом на движении 5px, не teоретически.
    jitter_distance_scale = min(1.0, distance / max(cfg.min_distance_for_curve, 1e-6))
    for i in range(cfg.steps + 1):
        t_linear = i / cfg.steps
        s = _minimum_jerk(t_linear)  # прогресс по кривой с человеко-подобным ускорением
        px, py = _quadratic_bezier((x0, y0), control, main_target, s)

        # Микро-дрожание: убывает к концу движения (ближе к цели — точнее),
        # и масштабируется под общую длину движения (см. комментарий выше).
        remaining = 1.0 - t_linear
        jitter_scale = remaining ** cfg.jitter_falloff * jitter_distance_scale
        if 0 < i < cfg.steps:  # не дрожим ровно в начальной и конечной точке
            px += rng.uniform(-cfg.jitter_px, cfg.jitter_px) * jitter_scale
            py += rng.uniform(-cfg.jitter_px, cfg.jitter_px) * jitter_scale

        path.append(MotionPoint(px, py, t_linear))

    if overshoot_target is not None:
        # Короткая коррекция от точки промаха к реальной цели — своя,
        # более короткая и быстрая дуга (человек поправляется резче, чем
        # выполняет основное движение).
        correction_cfg = HumanMotionConfig(
            steps=max(6, cfg.steps // 4),
            curve_strength=cfg.curve_strength * 0.4,
            jitter_px=cfg.jitter_px * 0.6,
            jitter_falloff=cfg.jitter_falloff,
            overshoot_probability=0.0,
            min_distance_for_curve=cfg.min_distance_for_curve,
            seed=rng.randint(0, 2**31),
        )
        correction = generate_path(main_target, (x1, y1), correction_cfg)
        # перенормируем t коррекции в хвост общего таймлайна (0.85..1.0)
        for p in correction[1:]:
            p.t = 0.85 + p.t * 0.15
        for p in path:
            p.t *= 0.85
        path.extend(correction[1:])

    # Гарантия точного попадания в цель — последняя точка всегда ровно (x1, y1),
    # независимо от накопленных погрешностей дрожания/коррекции.
    path[-1] = MotionPoint(x1, y1, 1.0)
    path[0] = MotionPoint(x0, y0, 0.0)
    return path


def path_length(path: list[MotionPoint]) -> float:
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += math.hypot(b.x - a.x, b.y - a.y)
    return total


def step_delays(path: list[MotionPoint], total_duration: float) -> list[float]:
    """Переводит t-метки точек пути в реальные паузы (сек) между шагами,
    сохраняя профиль скорости minimum-jerk (не равномерные интервалы!)."""
    delays = []
    for a, b in zip(path, path[1:]):
        delays.append(max(0.0, (b.t - a.t) * total_duration))
    return delays


# ---------------------------------------------------------------------------
# ДЕМО-РЕЖИМ (шоу): декоративные фигуры, НЕ используются для кликов/drag.
# Идея из разбора Hermes — держать её отдельно от боевой логики движения,
# потому что здесь допустима эстетика в ущерб "человечности" (человек не
# рисует идеальные спирали мышью), а для click/drag — наоборот, важна
# правдоподобность, а не красота.
# ---------------------------------------------------------------------------

def build_spiral_path(center: tuple[float, float], max_radius: float, *,
                       turns: float = 3.0, steps: int = 240) -> list[MotionPoint]:
    """Раскручивающаяся спираль — для демо-режима "разминка курсора"."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * turns * t
        r = max_radius * t
        points.append(MotionPoint(center[0] + r * math.cos(angle),
                                   center[1] + r * math.sin(angle), t))
    return points


def build_heart_path(center: tuple[float, float], size: float, *,
                      steps: int = 240) -> list[MotionPoint]:
    """Параметрическое сердце — декоративный демо-эффект."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * t
        x = 16 * math.sin(angle) ** 3
        y = (13 * math.cos(angle) - 5 * math.cos(2 * angle)
             - 2 * math.cos(3 * angle) - math.cos(4 * angle))
        points.append(MotionPoint(center[0] + x * size, center[1] - y * size, t))
    return points


def build_circle_path(center: tuple[float, float], radius: float, *,
                      turns: float = 1.0, steps: int = 240) -> list[MotionPoint]:
    """Окружность/спираль вокруг center — декоративный демо-эффект."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * turns * t
        points.append(MotionPoint(
            center[0] + radius * math.cos(angle),
            center[1] + radius * math.sin(angle),
            t,
        ))
    return points


def build_wander_path(bounds: tuple[float, float, float, float],
                      duration: float = 12.0, *, fps: int = 90,
                      rng: random.Random | None = None) -> list[MotionPoint]:
    """Плавное «гуляние» внутри bounds: кривая Лиссажу со случайными параметрами."""
    rng = rng or random.Random()
    x0, y0, w, h = bounds
    cx, cy = x0 + w / 2, y0 + h / 2
    ax, ay = w * 0.42, h * 0.42
    a, b = rng.choice((1, 2, 3)), rng.choice((1, 2, 3))
    if a == b:
        b += 1
    phase = rng.uniform(0.0, math.tau)
    steps = int(min(4000, max(16, duration * fps)))
    return [
        MotionPoint(
            cx + ax * math.sin(a * math.tau * i / (steps - 1) + phase),
            cy + ay * math.sin(b * math.tau * i / (steps - 1)),
            i / (steps - 1),
        )
        for i in range(steps)
    ]
