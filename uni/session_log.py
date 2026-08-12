from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path


class SessionLogger:
    """Append-only human-readable log of observable UNI interaction."""

    _SECRET_PATTERNS = (
        re.compile(r"(?i)(парол(?:ь|я)?\s*(?:[:=]|—|-)?\s*)\S+"),
        re.compile(r"(?i)((?:api[_ -]?key|token|секрет)\s*(?:[:=]|—|-)?\s*)\S+"),
        re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)\S+"),
    )

    def __init__(self, root: str | Path = ".uni-logs", enabled: bool = True) -> None:
        self.enabled = enabled
        self.root = Path(root).resolve()
        session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = self.root / session_id
        self.screenshot_dir = self.session_dir / "screenshots"
        self.log_path = self.session_dir / "session.log"
        self._lock = threading.Lock()
        if self.enabled:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            self.log("SYSTEM", "Сессия UNI начата")

    @classmethod
    def redact(cls, value: object) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        for pattern in cls._SECRET_PATTERNS:
            text = pattern.sub(r"\1[REDACTED]", text)
        return text[:12_000]

    def log(self, event: str, message: object) -> None:
        if not self.enabled:
            return
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        line = f"[{timestamp}] {event.upper():<10} {self.redact(message)}\n"
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(line)

