"""🤖 Сохранение успешных траекторий управления ПК под зрением.

Когда act_on_screen успешно выполнил цель, сохраняем траекторию
(goal -> шаги -> history) в memory/trajectories.jsonl. Позже на основе
накопленных траекторий можно повышать повторяющиеся паттерны до skills
(аддитивно, по образцу DPS-анализа: действие -> результат).

Файл trajectories.jsonl — runtime-данные (gitignored, как и весь memory/).
Генерируется/растёт на целевой машине.

НЕ является capability и НЕ импортирует capability. Чистая утилита логирования.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Путь к логу траекторий (runtime, в uni/memory/, как и calibration).
_TRAJ_DIR = Path(__file__).resolve().parents[1] / "memory"
_TRAJ_PATH = _TRAJ_DIR / "trajectories.jsonl"


def _ensure_dir() -> None:
    try:
        _TRAJ_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def save_trajectory(goal: str, steps: list[dict[str, Any]], history: list[str],
                    status: str = "success", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Добавить успешную траекторию в trajectories.jsonl (append).

    Возвращает записанную запись (dict).
    """
    record = {
        "goal": goal,
        "status": status,
        "steps": steps,
        "history": history,
        "meta": meta or {},
    }
    try:
        _ensure_dir()
        with open(_TRAJ_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # недоступна ФС (headless/readonly) — тихо пропускаем, не роняем клик
        pass
    return record


def load_trajectories() -> list[dict[str, Any]]:
    """Прочитать все траектории из trajectories.jsonl."""
    if not _TRAJ_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with open(_TRAJ_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def suggest_skill_from_trajectory(record: dict[str, Any]) -> dict[str, Any] | None:
    """Из одной успешной траектории сформировать черновик skill (аддитивно).

    Образец DPS: «цель -> последовательность шагов». Возвращает dict
    с именем skill, триггером (цель) и шагами (из history). Если данных
    недостаточно — None.
    """
    goal = (record.get("goal") or "").strip()
    history = record.get("history") or []
    if not goal or len(history) < 2:
        return None
    skill_name = "uni-action-" + _slugify(goal)
    return {
        "name": skill_name,
        "trigger": goal,
        "steps": history,
        "source": "trajectory",
        "note": "черновик, сгенерирован из trajectories.jsonl; требует ручного подтверждения",
    }


def _slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    s = "".join(out).strip("-")
    return s[:48] or "task"


if __name__ == "__main__":
    rec = save_trajectory(
        "открой блокнот",
        [{"action": "click", "x": 140, "y": 115}],
        ["шаг 1: сделала — клик по (140,115)", "шаг 1: проверила — цель достигнута ✅"],
    )
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    print("total trajectories:", len(load_trajectories()))
