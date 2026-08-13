"""Единый механизм аварийной остановки (P0.3 / B5).

Потокобезопасный флаг остановки. Используется там, где нужно
прервать длинные действия (самотест, future computer_vision_agent).
Автономный режим (autonomous.py) использует свой SessionState.stopped —
этот класс НЕ дублирует его, а даёт лёгкий общий примитив для остальных мест.
"""
from __future__ import annotations

import threading


class StopController:
    def __init__(self) -> None:
        self._stop_flag = False
        self._lock = threading.Lock()

    def stop(self) -> None:
        with self._lock:
            self._stop_flag = True

    def is_stopped(self) -> bool:
        with self._lock:
            return self._stop_flag

    def reset(self) -> None:
        with self._lock:
            self._stop_flag = False
