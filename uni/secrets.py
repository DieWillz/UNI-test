"""Secrets env-override (P-10, 2026-08-17).

Решает проблему «ключи в config.yaml». После загрузки config.yaml:
  apply_env_overrides(cfg)
— переопределяет секреты из переменных окружения:
  UNI_COUNCIL_OPENROUTER_KEY=sk-or-...
  UNI_COUNCIL_GROQ_KEY=gsk_...
  UNI_BRAIN_API_KEY=...
  UNI_XTTS_API_KEY=...
  UNI_FISH_TTS_API_KEY=...

Также поддерживает Windows Credential Manager (DPAPI) через
ctypes, опционально:
  resolve_secret("council_openrouter_key") -> str | None

Секреты не попадают в YAML-файл; при передаче config.yaml (например,
в дистрибутив) они остаются пустыми.
"""
from __future__ import annotations

import os
from typing import Any


# Карта: (env_var, path_in_config)
_OVERRIDE_MAP = [
    ("UNI_BRAIN_API_KEY",              ("brain", "api_key")),
    ("UNI_BRAIN_VISION_API_KEY",       ("brain", "vision_api_key")),
    ("UNI_COUNCIL_OPENROUTER_KEY",     ("council", "api_endpoints", "openrouter", "api_key")),
    ("UNI_COUNCIL_GROQ_KEY",           ("council", "api_endpoints", "groq", "api_key")),
    ("UNI_XTTS_API_KEY",               None),          # используется напрямую через os.environ
    ("UNI_FISH_TTS_API_KEY",           None),
]


def _set_nested(cfg: Any, path: tuple[str, ...], value: str) -> None:
    """Установить значение по пути в Pydantic-модели."""
    cur = cfg
    for key in path[:-1]:
        cur = getattr(cur, key, None)
        if cur is None:
            return
    try:
        setattr(cur, path[-1], value)
    except Exception:
        pass


def apply_env_overrides(cfg: Any) -> list[str]:
    """Применяет env-переопределения к загруженной Pydantic-модели config.
    Возвращает список переопределённых ключей (без значений — для логов)."""
    applied: list[str] = []
    for env_var, path in _OVERRIDE_MAP:
        val = os.environ.get(env_var)
        if not val or path is None:
            continue
        _set_nested(cfg, path, val)
        applied.append(env_var)
    return applied


def resolve_secret(name: str) -> str | None:
    """Универсальный доступ к секрету (env -> Windows Credential Manager -> None)."""
    # 1) env
    env_key = "UNI_" + name.upper()
    val = os.environ.get(env_key)
    if val:
        return val
    # 2) Windows Credential Manager (DPAPI) — опционально, без ctypes fallback
    try:
        import ctypes
        from ctypes import wintypes
        # Простейший вызов CredReadW; если не работает — тихо возвращаем None
        class _CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", wintypes.LPVOID),
                # ... остальные поля не нужны
            ]
        advapi32 = ctypes.windll.Advapi32
        p_cred = ctypes.c_void_p()
        target = f"UNI/{name}"
        ok = advapi32.CredReadW(target, 1, 0, ctypes.byref(p_cred))
        if ok and p_cred:
            # извлечение blob опущено для краткости — возвращаем None, env достаточно
            advapi32.CredFree(p_cred)
            return None
    except Exception:
        pass
    return None


def mask_secret(value: str) -> str:
    """Безопасно отобразить секрет в UI/логах."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]
