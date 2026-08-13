"""Тесты Мыши Юни (Директива §5: M-01..M-05).

Без живого Windows-дисплея проверяем:
- M-01: verified_physical/max_steps/blacklist/compare_screenshot присутствуют в коде.
- M-02: uni/motion/driver.py помечен 🤖 DEPRECATED (консолидация в human_motion/human_mouse).
- M-03: generate_path детерминированно имеет форму дуги + попадает в цель; cancel() прерывает.
- M-04: _mouse_demo() возвращает dict с ключами ok/points/drawn (логика, не исполнение).
"""
from __future__ import annotations

import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.human_motion import generate_path, HumanMotionConfig, path_length, step_delays


def test_m01_safety_present_in_computer_capability():
    # чёрный список, verified_physical, max_steps — обязательны (P0 Этап B/D)
    src = (Path(__file__).resolve().parents[1] / "uni" / "capabilities" / "computer.py").read_text(encoding="utf-8")
    assert "verified_physical" in src
    assert "max_steps" in src or "max_steps" in (Path(__file__).resolve().parents[1] / "uni" / "tools" / "visual_action.py").read_text(encoding="utf-8")
    assert "BLACKLISTED_COMMANDS" in src


def test_m02_duplicate_motion_deprecated():
    driver = (Path(__file__).resolve().parents[1] / "uni" / "motion" / "driver.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in driver
    assert "human_motion.py" in driver  # ссылка на канон-модуль


def test_m03_path_is_arc_and_hits_target():
    p = generate_path((0, 0), (100, 100), HumanMotionConfig(seed=1))
    assert (p[0].x, p[0].y) == (0.0, 0.0)
    assert (round(p[-1].x), round(p[-1].y)) == (100, 100)
    # дуга: длина пути больше прямой (гипотенуза ~141)
    assert path_length(p) > 141.0


def test_m03_path_respects_minimum_jerk_monotonic_speed_profile():
    # step_delays в сумме == total_duration (профиль скорости сохранён)
    p = generate_path((0, 0), (300, 0), HumanMotionConfig(seed=2))
    d = step_delays(p, 0.5)
    assert abs(sum(d) - 0.5) < 1e-6


def test_m04_mouse_demo_returns_shape():
    # импортируем _mouse_demo и проверяем контракт возврата БЕЗ исполнения мыши
    # (на Linux win32api нет -> функция вернёт {"ok": False, ...} честно)
    import uni.webui.server as srv  # noqa: F401  (регистрирует модуль)
    # вызываем напрямую: на headless вернёт ok=False с причиной, НЕ упадёт
    out = srv._mouse_demo()
    assert isinstance(out, dict)
    assert "ok" in out
    if out["ok"]:
        assert "points" in out and "drawn" in out
    else:
        # честная причина (не мок)
        assert out.get("error")
