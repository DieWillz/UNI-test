"""Plugin discovery via entry-points + local uni_plugins/ (P-16, 2026-08-17).

Использование:
  from uni.plugins import discover_plugins
  plugins = discover_plugins()
  # -> [{"name": "...", "module": "...", "class": "...", "source": "entry_point|local"}]

Сторонние capabilities регистрируются через pyproject.toml:
  [project.entry-points."uni.capabilities"]
  my_custom_cap = "my_pkg.capability:MyCustomCapability"

Локальные plugins (для разработки без установки):
  UNI_plugins/my_custom.py  (с классом MyCustomCapability)

Правило ADR-0005 сохраняется: plugin не импортирует другие capabilities.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

try:
    if sys.version_info >= (3, 10):
        from importlib.metadata import entry_points
    else:
        from importlib_metadata import entry_points  # type: ignore
except Exception:
    entry_points = None  # type: ignore

_CACHE: list[dict[str, Any]] | None = None


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


def _discover_entry_points() -> list[dict[str, Any]]:
    if entry_points is None:
        return []
    out: list[dict[str, Any]] = []
    try:
        # 3.10+: entry_points(group=...)
        try:
            eps = entry_points(group="uni.capabilities")
        except TypeError:
            # 3.9: entry_points() -> dict
            all_eps = entry_points()
            eps = all_eps.get("uni.capabilities", [])
    except Exception:
        return []
    for ep in eps:
        module_name = getattr(ep, "module", "") or ""
        attr_name = getattr(ep, "attr", "") or ""
        if not module_name:
            # fallback: parse value = "module:attr"
            value = getattr(ep, "value", "")
            if ":" in value:
                module_name, attr_name = value.split(":", 1)
        out.append({
            "name": getattr(ep, "name", ""),
            "module": module_name,
            "class": attr_name,
            "source": "entry_point",
        })
    return out


def _discover_local() -> list[dict[str, Any]]:
    """Сканирует UNI_plugins/ (или uni_plugins/) на .py-файлы."""
    out: list[dict[str, Any]] = []
    for candidate in (Path("UNI_plugins"), Path("uni_plugins")):
        if not candidate.is_dir():
            continue
        for f in sorted(candidate.glob("*.py")):
            if f.name.startswith("_"):
                continue
            out.append({
                "name": f.stem,
                "module": f"{candidate.name}.{f.stem}",
                "class": "",
                "source": "local",
                "path": str(f),
            })
    return out


def discover_plugins() -> list[dict[str, Any]]:
    """Возвращает список всех зарегистрированных plugins (core + entry + local)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    core = [{"name": "core", "module": "uni.capabilities", "class": "*", "source": "core"}]
    _CACHE = core + _discover_entry_points() + _discover_local()
    return _CACHE


def load_plugin_class(name: str) -> type | None:
    """Загружает класс capability plugin по имени. Возвращает None при ошибке."""
    for p in discover_plugins():
        if p["name"] == name and p.get("class") and p.get("module"):
            try:
                mod = importlib.import_module(p["module"])
                return getattr(mod, p["class"], None)
            except Exception:
                return None
    return None
