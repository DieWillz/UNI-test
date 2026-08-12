from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class WorkingMemory:
    """Small persistent memory for explicit facts and complete dialogue turns."""

    VERSION = 2
    _SECRET_PATTERNS = (
        re.compile(r"(?i)(парол(?:ь|я)?\s*(?:[:=]|—|-)?\s*)\S+"),
        re.compile(r"(?i)((?:api[_ -]?key|token|секрет)\s*(?:[:=]|—|-)?\s*)\S+"),
        re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)\S+"),
    )
    _HALLUCINATION_MARKERS = (
        "редактор субтитров",
        "корректор а.",
        "корректор н.",
        "субтитры сделал",
        "субтитры создавал",
    )

    def __init__(self, path: str | Path = "memory/working.json", max_dialogue_turns: int = 50):
        self.path = Path(path)
        self.max_dialogue_turns = max(5, min(int(max_dialogue_turns), 500))
        self.data: dict[str, Any] = self._empty_data()
        self._transient: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.load()

    @classmethod
    def _empty_data(cls) -> dict[str, Any]:
        return {"version": cls.VERSION, "facts": {}, "dialogue": []}

    @classmethod
    def _redact(cls, value: object) -> str:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        for pattern in cls._SECRET_PATTERNS:
            text = pattern.sub(r"\1[REDACTED]", text)
        return text[:12_000]

    @classmethod
    def _is_dialogue_text(cls, value: str) -> bool:
        normalized = " ".join(value.casefold().split())
        return bool(normalized) and not any(marker in normalized for marker in cls._HALLUCINATION_MARKERS)

    def _backup_legacy(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.stem}.legacy-{timestamp}{self.path.suffix}")
        counter = 1
        while backup.exists():
            backup = self.path.with_name(
                f"{self.path.stem}.legacy-{timestamp}-{counter}{self.path.suffix}"
            )
            counter += 1
        shutil.copy2(self.path, backup)
        return backup

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self.data = self._empty_data()
                return
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._backup_legacy()
                self.data = self._empty_data()
                self.persist()
                return

            if isinstance(loaded, dict) and loaded.get("version") == self.VERSION:
                facts = loaded.get("facts") if isinstance(loaded.get("facts"), dict) else {}
                dialogue = loaded.get("dialogue") if isinstance(loaded.get("dialogue"), list) else []
                self.data = {
                    "version": self.VERSION,
                    "facts": facts,
                    "dialogue": dialogue[-self.max_dialogue_turns :],
                }
                return

            self._backup_legacy()
            legacy_facts = {}
            if isinstance(loaded, dict):
                legacy_facts = {
                    str(key): value
                    for key, value in loaded.items()
                    if not str(key).startswith(("_", "last_"))
                }
            self.data = self._empty_data()
            self.data["facts"] = legacy_facts
            self.persist()

    def persist(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                temporary.write_text(
                    json.dumps(self.data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                os.replace(temporary, self.path)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def set(self, key: str, value: Any) -> None:
        clean_key = str(key).strip()
        if not clean_key:
            return
        if clean_key.startswith(("_", "last_")):
            self._transient[clean_key] = value
            return
        if isinstance(value, str):
            value = self._redact(value)
        with self._lock:
            self.data["facts"][clean_key] = value
            self.persist()

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._transient:
            return self._transient[key]
        return self.data["facts"].get(key, default)

    def delete(self, key: str) -> None:
        self._transient.pop(key, None)
        with self._lock:
            if key in self.data["facts"]:
                del self.data["facts"][key]
                self.persist()

    def list_keys(self) -> list[str]:
        return list(self.data["facts"].keys())

    def clear(self) -> None:
        with self._lock:
            self._transient.clear()
            self.data = self._empty_data()
            self.persist()

    def append_exchange(self, user: str, assistant: str) -> bool:
        clean_user = self._redact(user)
        clean_assistant = self._redact(assistant)
        if not self._is_dialogue_text(clean_user) or not self._is_dialogue_text(clean_assistant):
            return False
        exchange = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "user": clean_user,
            "assistant": clean_assistant,
        }
        with self._lock:
            dialogue = self.data["dialogue"]
            dialogue.append(exchange)
            self.data["dialogue"] = dialogue[-self.max_dialogue_turns :]
            self.persist()
        return True

    def recent_messages(self, limit: int = 8) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        exchanges = self.data["dialogue"][-max(0, limit // 2) :]
        for exchange in exchanges:
            if not isinstance(exchange, dict):
                continue
            user = exchange.get("user")
            assistant = exchange.get("assistant")
            if isinstance(user, str) and isinstance(assistant, str):
                messages.extend(
                    [
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": assistant},
                    ]
                )
        return messages[-limit:]

    def get_context(self, max_tokens: int = 4000) -> str:
        budget = max(100, int(max_tokens) * 4)
        lines: list[str] = []
        total = 0
        for key, value in self.data["facts"].items():
            line = f"{key}: {value}"
            if total + len(line) + 1 > budget:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines) or "Нет сохранённых фактов"
