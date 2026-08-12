"""Тест локального fallback для vision (B-04).

Проверяет:
- uia_find_element / uia_describe тихо возвращают None, когда uiautomation недоступен;
- uia_find_element возвращает dict с координатами при мокнутом uiautomation;
- ocr_available() возвращает bool (не падает).
"""

from __future__ import annotations

from unittest import mock

from uni.tools import local_vision_fallback as lvf


def test_uia_find_element_none_when_uia_missing():
    # uiautomation не установлен -> None
    with mock.patch.object(lvf, "_import_uiautomation", return_value=None):
        assert lvf.uia_find_element("открой блокнот") is None


def test_uia_describe_none_when_uia_missing():
    with mock.patch.object(lvf, "_import_uiautomation", return_value=None):
        assert lvf.uia_describe() is None


def test_uia_find_element_returns_coords_with_mock():
    # Минимальный мок uiautomation: ControlType, NameCondition, AndCondition,
    # GetRootControl, FindFirst, BoundingRectangle, TreeScope.
    class _Rect:
        def __init__(self, l, t, r, b): self.left, self.top, self.right, self.bottom = l, t, r, b
        def width(self): return self.right - self.left
        def height(self): return self.bottom - self.top
    class _El:
        Name = "Блокнот"
        ControlTypeName = "WindowControl"
        BoundingRectangle = _Rect(100, 100, 400, 300)
    class _CtrlType:
        ButtonControl = "Button"
        EditControl = "Edit"
    fake_uia = mock.MagicMock()
    fake_uia.ControlType.ButtonControl = "Button"
    fake_uia.ControlType.EditControl = "Edit"
    fake_uia.TreeScope = mock.MagicMock()
    fake_uia.NameCondition.return_value = "NameCond"
    fake_uia.AndCondition.return_value = "AndCond"
    root = mock.MagicMock()
    root.FindFirst.return_value = _El()
    fake_uia.GetRootControl.return_value = root

    # подменяем модуль uiautomation, чтобы `from uiautomation import TreeScope` работал
    import sys
    with mock.patch.dict(sys.modules, {"uiautomation": fake_uia}):
        res = lvf.uia_find_element("кнопка блокнот")
    assert res is not None
    assert res["x"] == 100 and res["y"] == 100
    assert res["width"] == 300 and res["height"] == 200
    assert res["confidence"] == 0.75
    assert res["source"] == "uia"


def test_uia_find_element_none_when_no_candidates():
    fake_uia = mock.MagicMock()
    fake_uia.ControlType.ButtonControl = "Button"
    fake_uia.NameCondition.return_value = "NameCond"
    fake_uia.TreeScope = mock.MagicMock()
    root = mock.MagicMock()
    root.FindFirst.return_value = None  # ничего не найдено
    fake_uia.GetRootControl.return_value = root

    import sys
    with mock.patch.dict(sys.modules, {"uiautomation": fake_uia}):
        assert lvf.uia_find_element("кнопка сохранить") is None


def test_ocr_available_returns_bool():
    # не должно падать в любом окружении
    assert isinstance(lvf.ocr_available(), bool)
