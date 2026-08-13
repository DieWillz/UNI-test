"""Файловые lock-файлы (P1.4 / D4) — защита от конкурентных действий.

Простая реализация через .lock-файл рядом с целевым. Не блокирует
поток (non-blocking): acquire_lock возвращает False, если lock уже есть.
"""
from __future__ import annotations

import os
from pathlib import Path


def acquire_lock(file_path: str, timeout: float = 0.0) -> bool:
    """Попытаться занять lock. Возвращает True, если получилось."""
    lock_path = f"{file_path}.lock"
    if Path(lock_path).exists():
        return False
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write("locked")
        return True
    except Exception:
        return False


def release_lock(file_path: str) -> None:
    """Снять lock (игнорирует ошибки)."""
    lock_path = f"{file_path}.lock"
    try:
        os.remove(lock_path)
    except Exception:
        pass
