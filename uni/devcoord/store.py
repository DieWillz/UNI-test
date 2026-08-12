from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from uni.devcoord.models import CoordinatorEvent, DevelopmentTask


class CoordinationStore:
    VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"version": self.VERSION, "tasks": {}, "events": []})

    def _read(self) -> dict[str, Any]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != self.VERSION:
            raise ValueError("unsupported coordination store version")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def save_task(self, task: DevelopmentTask) -> None:
        with self._lock:
            data = self._read()
            data["tasks"][task.id] = task.model_dump(mode="json")
            self._write(data)

    def get_task(self, task_id: str) -> DevelopmentTask:
        with self._lock:
            raw = self._read()["tasks"].get(task_id)
        if raw is None:
            raise KeyError(f"unknown task: {task_id}")
        return DevelopmentTask.model_validate(raw)

    def list_tasks(self) -> list[DevelopmentTask]:
        with self._lock:
            values = list(self._read()["tasks"].values())
        return [DevelopmentTask.model_validate(value) for value in values]

    def append_event(self, event: CoordinatorEvent) -> None:
        with self._lock:
            data = self._read()
            events = data["events"]
            events.append(event.model_dump(mode="json"))
            data["events"] = events[-5000:]
            self._write(data)

    def events_for(self, task_id: str) -> list[CoordinatorEvent]:
        with self._lock:
            values = [item for item in self._read()["events"] if item.get("task_id") == task_id]
        return [CoordinatorEvent.model_validate(value) for value in values]
