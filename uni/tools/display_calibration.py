"""🤖 Калибровка DPI / мульти-монитор для human_mouse.

Проблема: vision (скриншот/VLM) возвращает координаты в **логических** пикселях
(с учётом DPI-скейлинга Windows, например 150% → логический экран 1920×1080,
физический 2880×1620). А win32api.SetCursorPos() работает в **физических**
пикселях виртуального экрана (объединённого, со смещениями мониторов: левый
монитор может начинаться с отрицательного X). Без пересчёта мышь кликает мимо
(промах из-за DPI/второго монитора), что и фиксирует move_to_verified().

Этот модуль строит профиль mouse_display_profile.json:
  - для каждого монитора: logical_rect, physical_rect, dpi_scale, primary
  - функция to_physical(logical_x, logical_y) -> (phys_x, phys_y)

На не-Windows / headless — профиль {available:false}, to_physical = identity
(не ломает тесты и работу без дисплея).

НЕ является capability и НЕ импортирует capability — чистая утилита координат.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any

# Путь к профилю калибровки (memory/calibration/...).
_CALIB_DIR = Path(__file__).resolve().parents[1] / "memory" / "calibration"
_CALIB_PATH = _CALIB_DIR / "mouse_display_profile.json"

# --- win32 константы (используются только на Windows) ---
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _windows_dpi_per_monitor() -> list[dict[str, Any]]:
    """Считать физические rect'ы и DPI каждого монитора через user32/SHCore.

    Возвращает список мониторов:
        {"physical_left", "physical_top", "physical_right", "physical_bottom",
         "dpi_scale", "primary"}
    Логический rect вычисляется как physical / dpi_scale.
    """
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        shcore = ctypes.windll.shcore  # type: ignore[attr-defined]
    except AttributeError:
        return []

    monitors: list[dict[str, Any]] = []

    MONITOR_DEFAULTTONEAREST = 2

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    def _enum_proc(hmonitor, hdc, lprect, lparam):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return 1
        # DPI через шкалу (MDT_EFFECTIVE_DPI = 0)
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        scale = round(dpi_x.value / 96.0, 3)
        monitors.append({
            "physical_left": info.rcMonitor.left,
            "physical_top": info.rcMonitor.top,
            "physical_right": info.rcMonitor.right,
            "physical_bottom": info.rcMonitor.bottom,
            "dpi_scale": scale,
            "primary": bool(info.dwFlags & 1),
        })
        return 1

    ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double)
    if not user32.EnumDisplayMonitors(0, 0, ENUMPROC(_enum_proc), 0):
        return []
    return monitors


def build_profile() -> dict[str, Any]:
    """Построить и вернуть профиль калибровки (без записи на диск)."""
    monitors = _windows_dpi_per_monitor()
    if not monitors:
        # Не-Windows / headless / нет win32 — профиль недоступен.
        return {
            "available": False,
            "reason": "win32/SHCore недоступен (не-Windows или headless)",
            "monitors": [],
        }

    enriched = []
    for m in monitors:
        phys_w = m["physical_right"] - m["physical_left"]
        phys_h = m["physical_bottom"] - m["physical_top"]
        scale = m["dpi_scale"] or 1.0
        enriched.append({
            **m,
            "logical_left": m["physical_left"],
            "logical_top": m["physical_top"],
            "logical_width": int(round(phys_w / scale)),
            "logical_height": int(round(phys_h / scale)),
        })

    # Виртуальный экран (объединённый) в физических пикселях.
    virt_left = min(m["physical_left"] for m in monitors)
    virt_top = min(m["physical_top"] for m in monitors)
    virt_right = max(m["physical_right"] for m in monitors)
    virt_bottom = max(m["physical_bottom"] for m in monitors)

    return {
        "available": True,
        "virtual_physical": {
            "left": virt_left, "top": virt_top,
            "right": virt_right, "bottom": virt_bottom,
        },
        "monitors": enriched,
    }


def save_profile(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Построить профиль и сохранить в memory/calibration/mouse_display_profile.json."""
    profile = profile or build_profile()
    _CALIB_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return profile


def load_profile() -> dict[str, Any]:
    """Загрузить сохранённый профиль (или построить, если файла нет)."""
    if _CALIB_PATH.exists():
        try:
            with open(_CALIB_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return build_profile()


def to_physical(x: int, y: int, profile: dict[str, Any] | None = None) -> tuple[int, int]:
    """Перевести логические координаты (из vision) в физические (для SetCursorPos).

    Алгоритм:
      1. Найти монитор, в чей ЛОГИЧЕСКИЙ rect попадает (x, y).
      2. Сместить в локальные логические координаты монитора.
      3. Умножить на dpi_scale -> физические локальные.
      4. Добавить физическое смещение монитора (учёт виртуального экрана).

    Если профиль недоступен или монитор не найден — возвращаем (x, y) как есть
    (identity), чтобы не ломать поведение без дисплея / на одном мониторе 100%.
    """
    if profile is None:
        profile = load_profile()
    if not profile.get("available"):
        return int(x), int(y)

    monitors = profile.get("monitors", [])
    for m in monitors:
        ll, lt = m["logical_left"], m["logical_top"]
        lw, lh = m["logical_width"], m["logical_height"]
        # границы логического rect монитора (в виртуальных логических координатах)
        if ll <= x <= ll + lw and lt <= y <= lt + lh:
            local_lx = x - ll
            local_ly = y - lt
            scale = m["dpi_scale"] or 1.0
            phys_x = m["physical_left"] + int(round(local_lx * scale))
            phys_y = m["physical_top"] + int(round(local_ly * scale))
            return int(phys_x), int(phys_y)

    # Не попали ни в один монитор (например, за пределами) — identity.
    return int(x), int(y)


def to_logical(px: int, py: int, profile: dict[str, Any] | None = None) -> tuple[int, int]:
    """Обратное преобразование: физические -> логические (для проверки позиции)."""
    if profile is None:
        profile = load_profile()
    if not profile.get("available"):
        return int(px), int(py)

    for m in profile.get("monitors", []):
        pl, pt = m["physical_left"], m["physical_top"]
        pr, pb = m["physical_right"], m["physical_bottom"]
        if pl <= px <= pr and pt <= py <= pb:
            local_px = px - pl
            local_py = py - pt
            scale = m["dpi_scale"] or 1.0
            log_x = m["logical_left"] + int(round(local_px / scale))
            log_y = m["logical_top"] + int(round(local_py / scale))
            return int(log_x), int(log_y)
    return int(px), int(py)


if __name__ == "__main__":
    prof = save_profile()
    print(json.dumps(prof, ensure_ascii=False, indent=2))
