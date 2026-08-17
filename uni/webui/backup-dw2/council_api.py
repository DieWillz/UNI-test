"""Гибридный слой «отправка заданий участникам Совета» для UNI WebUI.

Расширяет существующий реестр ``uni.council.participants.DEFAULT_PARTICIPANTS``
(НЕ дублирует его — config.yaml.council.members не заводим). Участник с
прямым API + доступным ключом ходит сам (реальный запрос через ApiProvider);
остальные (browser/codex без ключа, api без ключа) помечаются ``manual`` —
интерфейс даёт скопировать задание и вставить ответ вручную. Это закрывает
боль ручного релея между 7 ИИ без требования платных ключей у владельца.

Сохраняет раунды в ``.uni-logs/rounds/round_NNN.json`` — переживают перезапуск.
Не ломает существующий SSE-маршрут POST /api/round/start.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import asyncio

from uni.council.participants import DEFAULT_PARTICIPANTS
from uni.council.provider import ApiProvider, build_provider

_ROOT = Path(__file__).resolve().parents[2]
_ROUNDS_DIR = _ROOT / ".uni-logs" / "rounds"


def _endpoint_ready(spec: dict[str, Any]) -> bool:
    """api-участник готов ходить сам, если endpoint резолвится с непустым ключом."""
    if spec.get("transport") != "api" or not spec.get("endpoint"):
        return False
    from uni.council._keys import resolve_endpoint

    try:
        from ..config import load_config

        cfg = load_config()
    except Exception:
        cfg = None
    ep = resolve_endpoint(spec["endpoint"], cfg)
    if not ep:
        return False
    return bool(ep.get("api_key"))


def list_members() -> list[dict[str, Any]]:
    """Список участников с флагами type/ready для интерфейса."""
    members: list[dict[str, Any]] = []
    for spec in DEFAULT_PARTICIPANTS:
        transport = spec.get("transport", "api")
        ready = _endpoint_ready(spec)
        # manual = не может ходить по API сам (browser/codex или api без ключа)
        mtype = "api" if transport == "api" else "manual"
        members.append(
            {
                "name": spec["name"],
                "role": spec.get("role", ""),
                "transport": transport,
                "type": mtype,
                "ready": ready,
                "model": spec.get("model", ""),
            }
        )
    return members


def _next_round_id() -> int:
    _ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for p in _ROUNDS_DIR.glob("round_*.json")
                if (m := re.match(r"round_(\d+)\.json", p.name))]
    return (max(existing) + 1) if existing else 1


def _build_task_text(task: str, member: dict[str, Any]) -> str:
    return (
        f"Задание для участника «{member['name']}» ({member.get('role', '')}):\n\n"
        f"{task}\n\n---\nОтветь развёрнуто, в рамках своей роли. Подпиши ответ."
    )


async def create_round(task: str, members: list[str] | None = None) -> dict[str, Any]:
    """Создать раунд. Для ready-api — реальный запрос; иначе task_text для копипаста."""
    members = members or [m["name"] for m in list_members()]
    selected = [m for m in list_members() if m["name"] in members]
    if not selected:
        selected = list_members()

    round_id = _next_round_id()
    _ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    path = _ROUNDS_DIR / f"round_{round_id:03d}.json"

    responses: dict[str, Any] = {}
    for member in selected:
        entry = {
            "name": member["name"],
            "role": member.get("role", ""),
            "type": member["type"],
            "status": "pending",
            "text": "",
            "error": None,
        }
        if member["type"] == "api" and member["ready"]:
            entry["status"] = "running"
            responses[member["name"]] = entry
        else:
            # manual: готовим task_text, ответ придёт через paste
            entry["task_text"] = _build_task_text(task, member)
            entry["status"] = "manual_wait"
            responses[member["name"]] = entry

    record = {
        "round_id": round_id,
        "task": task,
        "created_at": time.time(),
        "members": responses,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # Реальные API-запросы параллельно (asyncio.gather), не блокируя manual-участников
    api_members = [m for m in selected if m["type"] == "api" and m["ready"]]
    if api_members:
        await _run_api_members(task, api_members, record, path)

    return {
        "round_id": round_id,
        "task": task,
        "members": [
            {
                "name": m["name"],
                "type": m["type"],
                "status": responses[m["name"]]["status"],
                "task_text": responses[m["name"]].get("task_text"),
            }
            for m in selected
        ],
        "manual_count": sum(1 for m in selected if responses[m["name"]]["status"] == "manual_wait"),
    }


async def _run_api_members(task: str, api_members: list[dict], record: dict, path: Path) -> None:
    from uni.council.participants import DEFAULT_PARTICIPANTS

    # сопоставим spec по имени
    spec_by_name = {s["name"]: s for s in DEFAULT_PARTICIPANTS}
    providers = []
    for m in api_members:
        spec = dict(spec_by_name.get(m["name"], {}))
        from uni.council._keys import resolve_endpoint

        try:
            from ..config import load_config

            cfg = load_config()
        except Exception:
            cfg = None
        ep = resolve_endpoint(spec["endpoint"], cfg) or {}
        spec["base_url"] = ep.get("base_url", "")
        spec["api_key"] = ep.get("api_key", "")
        spec["model"] = spec.get("model", "")
        providers.append((m["name"], ApiProvider(
            base_url=spec["base_url"], api_key=spec["api_key"], model=spec["model"],
            timeout_seconds=60.0,
        )))

    async def _ask_one(name: str, prov: ApiProvider):
        reply = await prov.ask(name, task)
        await prov.close()
        return name, reply

    results = await asyncio.gather(*[_ask_one(n, p) for n, p in providers], return_exceptions=True)
    for name, res in results:
        if isinstance(res, Exception):
            record["members"][name].update(status="error", error=f"{type(res).__name__}: {res}")
        else:
            record["members"][name].update(
                status="done", text=res.text, error=res.error, model=res.model,
            )
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def get_round(round_id: int) -> dict[str, Any] | None:
    path = _ROUNDS_DIR / f"round_{round_id:03d}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def paste_response(round_id: int, member: str, text: str) -> dict[str, Any] | None:
    path = _ROUNDS_DIR / f"round_{round_id:03d}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if member not in record["members"]:
        return None
    record["members"][member].update(status="done", text=text, pasted=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
