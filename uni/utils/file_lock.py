"""Файловые lock-файлы (P1.4 / D4) — защита от конкурентных действий.

Lock создаётся атомарно через O_CREAT | O_EXCL. По умолчанию acquire_lock
не блокирует; timeout > 0 позволяет кратко дождаться освобождения lock.
"""
from __future__ import annotations

import os
import time


def acquire_lock(file_path: str, timeout: float = 0.0) -> bool:
    """Атомарно занять lock, ожидая до ``timeout`` секунд при необходимости."""
    lock_path = f"{file_path}.lock"
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.01, remaining))
        except OSError:
            return False

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("locked")
    except OSError:
        try:
            os.remove(lock_path)
        except OSError:
            pass
        return False
    return True


def release_lock(file_path: str) -> None:
    """Снять lock (игнорирует ошибки)."""
    lock_path = f"{file_path}.lock"
    try:
        os.remove(lock_path)
    except OSError:
        pass
