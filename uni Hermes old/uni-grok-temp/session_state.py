from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SessionState:
    """Shared, async-safe state for the autonomous (hands-free) mode.

    Vision, speech and device loops read/write the same instance so they can
    react to each other without going through a single global lock.
    """

    screen_desc: str = "неизвестно"
    screen_updated_at: float = 0.0
    intensity: int = 0
    pattern: str = "none"
    last_phrase: str = ""
    phrase_count: int = 0
    running: bool = True
    phase: str = "tease"
    phase_cycles: int = 0
    _stop: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def request_stop(self) -> None:
        self.running = False
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop
