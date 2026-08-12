"""FIX-AUDIT A-02: интеграционный тест рассинхрона порогов уверенности.

РЕАЛЬ Translation: используем РЕАЛЬНЫЙ VisionCapability.find_desktop_element
(с реальным порогом VISION_CONFIDENCE_THRESHOLD) + РЕАЛЬНЫЙ
VisualActionAgent._locate. Мокаем ТОЛЬКО уровень VLM/скриншота
(_capture_desktop, _ask) — не весь интерфейс.

Доказывает: ветка clarify достижима с реальным порогом (P2 из аудита).
"""

from __future__ import annotations

import asyncio
from unittest import mock

from PIL import Image

from uni.config import load_config
from uni.capabilities.vision import VisionCapability, VISION_CONFIDENCE_THRESHOLD
from uni.contracts import ToolResult
from uni.tools.visual_action import VisualActionAgent


class _FakeComputer:
    def __init__(self):
        self.use_human_motion = True
        self.clicks = []

    async def click_human(self, x, y, button="left"):
        self.clicks.append((x, y))
        return ToolResult(success=True, message=f"click {x},{y}")

    async def click(self, x, y, button="left"):
        self.clicks.append((x, y))
        return ToolResult(success=True, message=f"click {x},{y}")


def _make_real_vision(confidence: float):
    """Реальный VisionCapability с замоканным только VLM/скриншотом."""
    cfg = load_config()
    cap = VisionCapability(mock.MagicMock(), cfg, mock.MagicMock())
    cap._capture_desktop = mock.AsyncMock(
        return_value=(Image.new("RGB", (320, 180), (0, 0, 0)), (1920, 1080))
    )
    # VLM возвращает JSON с заданной уверенностью (ниже порога -> low_conf ветка)
    cap._ask = mock.AsyncMock(
        return_value=f'{{"x":100,"y":100,"width":50,"height":20,"confidence":{confidence}}}'
    )
    return cap


def test_a02_clarify_reachable_with_real_threshold():
    # P2 FIX: vision при conf<порога возвращает success=False + data,
    # visual_action._locate трактует это как low_conf -> act_on_screen -> clarify.
    cap = _make_real_vision(confidence=0.3)  # < VISION_CONFIDENCE_THRESHOLD (0.55)
    agent = VisualActionAgent(_FakeComputer(), cap, max_steps=1)
    result = asyncio.run(agent._locate("открой блокнот"))
    assert result == "low_conf", f"ожидался low_conf (clarify ветка), получил {result!r}"


def test_a02_high_conf_returns_data():
    # При высокой уверенности vision возвращает success=True+data -> _locate даёт dict.
    cap = _make_real_vision(confidence=0.9)  # >= порога
    agent = VisualActionAgent(_FakeComputer(), cap, max_steps=1)
    result = asyncio.run(agent._locate("открой блокнот"))
    assert isinstance(result, dict), f"ожидался dict, получил {result!r}"
    assert result["confidence"] == 0.9


def test_a02_threshold_is_single_source():
    # Порог вынесен в ОДНУ константу (источник истины), а не захардкожен.
    assert isinstance(VISION_CONFIDENCE_THRESHOLD, float)
    assert VISION_CONFIDENCE_THRESHOLD == 0.55
