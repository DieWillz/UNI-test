"""i18n — простой каталог сообщений (P-16, 2026-08-17).

Использование:
  from uni.i18n import t, set_locale
  set_locale("ru")
  t("mission.started")  # -> "Миссия запущена"
  set_locale("en")
  t("mission.started")  # -> "Mission started"

Локали лежат в uni/i18n/locales/{ru,en}.json.
Недостающие ключи возвращаются как есть (fallback на key).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_LOCALES_DIR = _HERE / "locales"

_CURRENT_LOCALE = "ru"
_CACHE: dict[str, dict[str, str]] = {}
_AVAILABLE: list[str] = []


def available_locales() -> list[str]:
    global _AVAILABLE
    if not _AVAILABLE:
        _AVAILABLE = sorted(
            p.stem for p in _LOCALES_DIR.glob("*.json") if p.is_file()
        )
        if not _AVAILABLE:
            _AVAILABLE = ["ru", "en"]
    return _AVAILABLE


def load_locale(locale: str) -> dict[str, str]:
    if locale in _CACHE:
        return _CACHE[locale]
    p = _LOCALES_DIR / f"{locale}.json"
    if not p.is_file():
        _CACHE[locale] = {}
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    flat: dict[str, str] = {}
    _flatten(data, "", flat)
    _CACHE[locale] = flat
    return flat


def _flatten(obj: Any, prefix: str, out: dict[str, str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _flatten(v, key, out)
            else:
                out[key] = str(v)


def set_locale(locale: str) -> str:
    global _CURRENT_LOCALE
    if locale in available_locales():
        _CURRENT_LOCALE = locale
    return _CURRENT_LOCALE


def get_locale() -> str:
    return _CURRENT_LOCALE


def t(key: str, **kwargs: Any) -> str:
    """Перевести ключ с текущей локалью. Недостающий key -> сам key."""
    catalog = load_locale(_CURRENT_LOCALE)
    text = catalog.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
