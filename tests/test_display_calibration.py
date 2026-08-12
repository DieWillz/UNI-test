"""Тест калибровки DPI/мульти-монитор (B-03).

Проверяет логику display_calibration.to_physical / to_logical на
синтетическом профиле (без реального win32), и что на недоступном
профиле функции ведут себя как identity (не ломают старое поведение).
"""

from __future__ import annotations

from uni.tools import display_calibration as dc


# Синтетический профиль: один монитор 100% DPI (identity) и DPI 150%.
_PROFILE_100 = {
    "available": True,
    "monitors": [
        {
            "physical_left": 0, "physical_top": 0,
            "physical_right": 1920, "physical_bottom": 1080,
            "dpi_scale": 1.0, "primary": True,
            "logical_left": 0, "logical_top": 0,
            "logical_width": 1920, "logical_height": 1080,
        }
    ],
}

_PROFILE_150 = {
    "available": True,
    "monitors": [
        {
            "physical_left": 0, "physical_top": 0,
            "physical_right": 2880, "physical_bottom": 1620,
            "dpi_scale": 1.5, "primary": True,
            "logical_left": 0, "logical_top": 0,
            "logical_width": 1920, "logical_height": 1080,
        }
    ],
}

# Второй монитор слева (отрицательные координаты в виртуальном экране).
_PROFILE_DUAL = {
    "available": True,
    "monitors": [
        {
            "physical_left": -1440, "physical_top": 0,
            "physical_right": 0, "physical_bottom": 900,
            "dpi_scale": 1.0, "primary": False,
            "logical_left": -1440, "logical_top": 0,
            "logical_width": 1440, "logical_height": 900,
        },
        {
            "physical_left": 0, "physical_top": 0,
            "physical_right": 1920, "physical_bottom": 1080,
            "dpi_scale": 1.0, "primary": True,
            "logical_left": 0, "logical_top": 0,
            "logical_width": 1920, "logical_height": 1080,
        },
    ],
}


def test_identity_when_unavailable():
    prof = {"available": False, "monitors": []}
    assert dc.to_physical(100, 100, prof) == (100, 100)
    assert dc.to_logical(100, 100, prof) == (100, 100)


def test_scale_100_identity():
    assert dc.to_physical(500, 400, _PROFILE_100) == (500, 400)
    assert dc.to_logical(500, 400, _PROFILE_100) == (500, 400)


def test_scale_150():
    # логический (100,100) -> физический (150,150)
    assert dc.to_physical(100, 100, _PROFILE_150) == (150, 150)
    # физический (150,150) -> логический (100,100)
    assert dc.to_logical(150, 150, _PROFILE_150) == (100, 100)


def test_dual_monitor_left():
    # логический (-100, 50) на левом мониторе -> физический (-100, 50) (scale 1.0)
    assert dc.to_physical(-100, 50, _PROFILE_DUAL) == (-100, 50)
    # логический (100, 50) на правом (primary) -> физический (100, 50)
    assert dc.to_physical(100, 50, _PROFILE_DUAL) == (100, 50)


def test_out_of_bounds_identity():
    # точка вне любого монитора -> не меняем (identity), чтобы не телепортировать
    assert dc.to_physical(99999, 99999, _PROFILE_100) == (99999, 99999)


def test_load_profile_fallback_on_headless():
    # на headless/не-Windows build_profile вернёт available=False; load_profile
    # не должен падать.
    prof = dc.build_profile()
    assert isinstance(prof, dict)
    assert "available" in prof
