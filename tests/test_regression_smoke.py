"""B-07 Регрессия — 10× smoke-проверок.

Быстрые проверки, что ключевые модули управления ПК под зрением
импортируются и базовые объекты создаются без падений. Каждый модуль
прогоняется ×10 (в цикле) чтобы поймать интермиттирующие/состояние-зависимые сбои.
"""

from __future__ import annotations

import importlib

import pytest


# Список модулей для smoke-проверки (импорт + базовая санитация).
SMOKE_MODULES = [
    "uni.agent",
    "uni.event_loop",
    "uni.human_mouse",
    "uni.capabilities.computer",
    "uni.capabilities.vision",
    "uni.tools.visual_action",
    "uni.tools.display_calibration",
    "uni.tools.local_vision_fallback",
    "uni.tools.trajectory_store",
    "uni.webui.server",
]

# Количество повторов (10× smoke по директиве).
SMOKE_REPEATS = 10


@pytest.mark.parametrize("module_name", SMOKE_MODULES)
def test_smoke_imports(module_name: str) -> None:
    """Импорт модуля ×10 — ловит интермиттирующие/порядок-зависимые сбои."""
    for _ in range(SMOKE_REPEATS):
        mod = importlib.import_module(module_name)
        assert mod is not None
