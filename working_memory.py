import json
from pathlib import Path
from typing import Any

class WorkingMemory:
    def __init__(self, path: str = "memory/working.json"):
        self.path = Path(path)
        self.data = {}
        self.load()

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.persist()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def get_context(self, max_tokens: int = 4000) -> str:
        items = []
        total = 0
        for k, v in self.data.items():
            if k.startswith("_"): continue
            s = f"{k}: {v}"
            if total + len(s) > max_tokens: break
            items.append(s)
            total += len(s)
        return "\n".join(items) or "Нет данных"

    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
