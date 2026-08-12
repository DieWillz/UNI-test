from __future__ import annotations

import asyncio
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
    # UI bridge: autonomous mode pushes {type:'phrase', text, audio_url} here;
    # the WebUI server drains it via SSE and the browser renders + plays audio.
    ui_events: asyncio.Queue | None = None
    # Async stop signal for the background loop (set by request_stop).
    stopped_event: asyncio.Event = field(default_factory=asyncio.Event)

    def request_stop(self) -> None:
        self.running = False
        self._stop = True
        try:
            self.stopped_event.set()
        except RuntimeError:
            # Event created outside a running loop; recreate lazily.
            self.stopped_event = asyncio.Event()
            self.stopped_event.set()

    @property
    def stopped(self) -> bool:
        return self._stop
