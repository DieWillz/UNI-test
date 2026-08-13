"""Тесты V-light зрения (Директива §4: V-01..V-06).

Без живого Windows-дисплея проверяем логику каскадов и валидаций:
- find_desktop_element_tier0: порядок UIA->OCR->DOM, каждый канал тихо None
  при недоступности (не падает); край UIA возвращает source-тег.
- region_diff: числовой дифф двух PNG (синтетические кадры).
- tier2_gpu_available: честно False без nvidia-smi (FileNotFoundError перехвачен).
- fail-closed: пустая цель -> not_found; blacklist в visual_action -> blocked.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest import mock

from uni.tools.local_vision_fallback import (
    find_desktop_element_tier0, winrt_ocr_available, ocr_available,
)
from uni.tools.visual_action import VisualActionAgent, _BLACKLIST


def test_tier0_order_uia_first():
    # UIA возвращает элемент -> он побеждает, OCR/DOM не вызываются
    uia_el = {"x": 1.0, "y": 2.0, "width": 10.0, "height": 5.0, "confidence": 0.8}
    with mock.patch("uni.tools.local_vision_fallback.uia_find_element", return_value=uia_el), \
         mock.patch("uni.tools.local_vision_fallback.ocr_find_text", return_value=None) as m_ocr, \
         mock.patch("uni.tools.local_vision_fallback.dom_find_element", return_value=None) as m_dom:
        res = find_desktop_element_tier0("Пуск")
        assert res["source"] == "uia"
        m_ocr.assert_not_called()  # OCR не вызван — UIA победил
        m_dom.assert_not_called()


def test_tier0_fallback_to_ocr_when_uia_none():
    ocr_el = {"x": 0.0, "y": 0.0, "width": 3.0, "height": 3.0, "confidence": 0.7, "source": "ocr"}
    with mock.patch("uni.tools.local_vision_fallback.uia_find_element", return_value=None), \
         mock.patch("uni.tools.local_vision_fallback.ocr_find_text", return_value=ocr_el), \
         mock.patch("uni.tools.local_vision_fallback.dom_find_element", return_value=None):
        res = find_desktop_element_tier0("найди текст привет")
        assert res["source"] == "ocr"


def test_tier0_all_none_returns_none():
    with mock.patch("uni.tools.local_vision_fallback.uia_find_element", return_value=None), \
         mock.patch("uni.tools.local_vision_fallback.ocr_find_text", return_value=None), \
         mock.patch("uni.tools.local_vision_fallback.dom_find_element", return_value=None):
        assert find_desktop_element_tier0("anything") is None


def test_tier0_channel_exception_is_safe():
    # если канал падает (нет библиотеки) — НЕ поднимает исключение наверх
    with mock.patch("uni.tools.local_vision_fallback.uia_find_element", side_effect=RuntimeError("no uia")), \
         mock.patch("uni.tools.local_vision_fallback.ocr_find_text", return_value=None), \
         mock.patch("uni.tools.local_vision_fallback.dom_find_element", return_value=None):
        assert find_desktop_element_tier0("x") is None


def test_winrt_ocr_reports_availability_honestly():
    # в этом окружении winrt скорее всего нет — проверяем, что функция НЕ падает
    ok, why = winrt_ocr_available()
    assert isinstance(ok, bool)
    # если False — причина содержит честное описание, а не пустоту
    if not ok:
        assert why


def test_region_diff_detects_change():
    from PIL import Image
    import numpy as np
    d = Path(__file__).resolve().parent / "_scratch_vision"
    d.mkdir(exist_ok=True)
    a = np.zeros((20, 20, 3), dtype=np.uint8)
    b = a.copy()
    b[5:10, 5:10] = 255  # внесли изменение
    pa = d / "a.png"; pb = d / "b.png"
    Image.fromarray(a).save(pa); Image.fromarray(b).save(pb)
    # region_diff импортируем из vision
    from uni.capabilities.vision import VisionCapability
    # создаём экземпляр без реального brain/config (метод pure-python)
    vc = VisionCapability.__new__(VisionCapability)
    changed = vc.region_diff(str(pa), str(pb), threshold=0.15)
    assert 0.0 < changed < 1.0
    pa.unlink(); pb.unlink()


def test_tier2_gpu_unavailable_without_nvidia():
    from uni.capabilities.vision import VisionCapability
    vc = VisionCapability.__new__(VisionCapability)

    class _Vision:
        tier2_min_vram_gb = 8
    class _Caps:
        vision = _Vision
    class _Cfg:
        capabilities = _Caps
    vc.config = _Cfg
    # nvidia-smi нет в PATH этого окружения -> FileNotFoundError -> (False, причина)
    ok, why = vc.tier2_gpu_available()
    assert ok is False and why


def test_visual_action_blacklist_blocked():
    # 🤖 V-05 fail-closed: опасная системная цель -> blocked, клик не производится
    agent = VisualActionAgent(computer=None, vision=None, max_steps=1)
    res = agent.run_for_test if hasattr(agent, "run_for_test") else None
    out = __import__("asyncio").run(agent.act_on_screen("format диск C:"))
    assert out["status"] == "blocked"


def test_visual_action_empty_goal_clarify():
    agent = VisualActionAgent(computer=None, vision=None, max_steps=1)
    out = __import__("asyncio").run(agent.act_on_screen(""))
    assert out["status"] == "clarify"


def test_blacklist_contains_dangerous():
    assert any(b in "format " for b in _BLACKLIST)
    assert "taskkill" in _BLACKLIST
