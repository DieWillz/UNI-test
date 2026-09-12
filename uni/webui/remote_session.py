from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RemoteRoomStore:
    """Thread-safe signaling/chat store. Tokens never enter persisted events."""

    runtime_dir: Path
    max_events: int = 500
    _events: list[dict[str, Any]] = field(default_factory=list, init=False)
    _next_id: int = field(default=1, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    @property
    def chat_path(self) -> Path:
        return self.runtime_dir / "remote_chat.jsonl"

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._next_id = 1

    def send(self, role: str, kind: str, payload: Any) -> dict[str, Any]:
        target = "controller" if role == "owner" else "owner"
        with self._lock:
            event = {
                "id": self._next_id,
                "kind": kind,
                "from": role,
                "target": target,
                "payload": payload,
                "time": time.time(),
            }
            self._next_id += 1
            self._events.append(event)
            del self._events[:-self.max_events]
        if kind == "chat":
            self._append_chat(event)
        return event

    def poll(self, role: str, after: int) -> list[dict[str, Any]]:
        with self._lock:
            return [e.copy() for e in self._events if e["id"] > after and e["target"] == role][-100:]

    def _append_chat(self, event: dict[str, Any]) -> None:
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            record = {k: event[k] for k in ("id", "from", "target", "payload", "time")}
            with self.chat_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
