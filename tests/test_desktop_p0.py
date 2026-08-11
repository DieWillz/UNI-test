"""Статические тесты P0-оверлея (D-01..D-04, D-08): структура и валидность.

Electron не установлен в CI-окружении, поэтому проверяем то, что проверяемо без
рантайма: наличие файлов, валидность JS (node --check), валидность package.json,
наличие SVG-состояний аватара, и что preload.js экспонирует window.uni (по исходнику).
Это proof of work без запуска Electron.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[1] / "uni" / "desktop"


def _node_check(path: Path) -> bool:
    try:
        r = subprocess.run([_node_exe(), "--check", str(path)],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _node_exe():
    # node должен быть в PATH
    return "node"


def test_desktop_files_exist():
    # D-01: структура uni/desktop/
    for f in ("package.json", "main.js", "preload.js",
             "renderer/index.html", "renderer/style.css",
             "renderer/app.js", "renderer/avatar.js", "PLAN.md"):
        assert (Path(_DESKTOP) / f).is_file(), f"нет файла {f}"


def test_avatar_states_exist():
    # D-08: 4 состояния аватара (SVG-плейсхолдеры)
    for s in ("idle", "speak", "listen", "think"):
        p = Path(_DESKTOP) / "assets" / f"avatar_{s}.svg"
        assert p.is_file(), f"нет avatar_{s}.svg"


def test_js_valid():
    # все JS файлы оверлея валидны (node --check)
    for f in ("main.js", "preload.js", "renderer/app.js", "renderer/avatar.js"):
        p = Path(_DESKTOP) / f
        assert _node_check(p), f"JS невалиден: {f}"


def test_package_json_valid():
    p = Path(_DESKTOP) / "package.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("main") == "main.js"
    assert "electron" in json.dumps(data.get("devDependencies", {}))


def test_preload_exposes_uni():
    # preload.js должен экспонировать window.uni через contextBridge
    src = (Path(_DESKTOP) / "preload.js").read_text(encoding="utf-8")
    assert "contextBridge.exposeInMainWorld" in src
    assert '"uni"' in src or "'uni'" in src


def test_click_through_wired():
    # D-03: main.js должен реагировать на hit-test -> setIgnoreMouseEvents
    main = (Path(_DESKTOP) / "main.js").read_text(encoding="utf-8")
    assert "hit-test" in main and "setIgnoreMouseEvents" in main


def test_bottom_position_wired():
    # D-04: позиция у нижней кромки
    main = (Path(_DESKTOP) / "main.js").read_text(encoding="utf-8")
    assert "placeAtBottomRight" in main or "workAreaSize" in main
