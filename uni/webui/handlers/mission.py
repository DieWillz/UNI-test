"""Длительные миссии Юни (P-03, 2026-08-17).

Эндпоинты:
  GET  /api/mission/current          — текущая активная миссия или {active:false}
  POST /api/mission/start            — старт миссии {goal, stages[], ...}
  POST /api/mission/step             — обновить этап
  POST /api/mission/complete         — завершить
  POST /api/mission/confirm_income   — подтвердить доход (fail-closed)
  POST /api/mission/add_cost         — добавить затраты

Состояние в runtime/missions/current.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from uni.contracts import Verification, VerificationStatus

from . import registry
from .events import publish_event

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_MISSION_PATH = _ROOT / "runtime" / "missions" / "current.json"


def _read_mission() -> dict[str, Any]:
    if not _MISSION_PATH.is_file():
        return {"active": False}
    try:
        return json.loads(_MISSION_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"active": False}


def _write_mission(data: dict[str, Any]) -> None:
    _MISSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.time()
    _MISSION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_body(handler) -> dict:
    try:
        return json.loads(
            (handler.rfile.read(int(handler.headers.get("Content-Length") or 0)) or b"{}").decode("utf-8")
        )
    except Exception:
        return {}


def _current(handler) -> None:
    handler._json(200, _read_mission())


def _start(handler) -> None:
    body = _read_body(handler)
    goal = str(body.get("goal") or "").strip()
    if not goal:
        handler._json(400, {"error": "goal required"}); return
    stages = body.get("stages") or ["исследование", "проверка вариантов", "выбор стратегии", "подготовка", "запуск"]
    data = {
        "active": True, "goal": goal, "stages": stages, "stage_index": 0,
        "status": "running", "verification": {"status": "not_verified"},
        "progress_pct": 0, "current_op": body.get("current_op") or stages[0],
        "confirmed_income": 0.0, "expected_income": 0.0, "costs": 0.0, "net": 0.0,
        "awaiting": body.get("awaiting") or [], "recent_actions": [],
        "started_at": time.time(),
        "trace": [{"stage": "COMMAND", "ts": time.time(), "summary": goal}],
    }
    _write_mission(data)
    publish_event({"type": "mission.started", "mission": data})
    handler._json(200, {"ok": True, "mission": data})


def _step(handler) -> None:
    data = _read_mission()
    if not data.get("active"):
        handler._json(409, {"error": "нет активной миссии"}); return
    body = _read_body(handler)
    if "stage_index" in body:
        data["stage_index"] = max(0, min(len(data.get("stages", [])) - 1, int(body["stage_index"])))
        if data["stages"] and data["stage_index"] < len(data["stages"]):
            data["current_op"] = data["stages"][data["stage_index"]]
    if "progress_pct" in body:
        data["progress_pct"] = max(0, min(100, int(body["progress_pct"])))
    if "current_op" in body:
        data["current_op"] = str(body["current_op"])
    if "expected_income" in body:
        data["expected_income"] = float(body["expected_income"])
    if "action" in body:
        action = {"ts": time.time(), "text": str(body["action"])[:200]}
        data.setdefault("recent_actions", []).append(action)
        data["recent_actions"] = data["recent_actions"][-20:]
        data.setdefault("trace", []).append({"stage": "ACTION", **action})
    data["net"] = float(data.get("confirmed_income", 0)) - float(data.get("costs", 0))
    _write_mission(data)
    publish_event({"type": "mission.updated", "mission": data})
    handler._json(200, {"ok": True, "mission": data})


def _confirm_income(handler) -> None:
    data = _read_mission()
    if not data.get("active"):
        handler._json(409, {"error": "нет активной миссии"}); return
    body = _read_body(handler)
    amount = float(body.get("amount", 0))
    if amount <= 0:
        handler._json(400, {"error": "amount must be > 0"}); return
    source = str(body.get("source") or "manual").strip()
    data["confirmed_income"] = float(data.get("confirmed_income", 0)) + amount
    data.setdefault("income_events", []).append({"ts": time.time(), "amount": amount, "source": source})
    data["net"] = float(data["confirmed_income"]) - float(data.get("costs", 0))
    _write_mission(data)
    publish_event({"type": "mission.income_confirmed", "amount": amount, "source": source})
    handler._json(200, {"ok": True, "mission": data})


def _add_cost(handler) -> None:
    data = _read_mission()
    if not data.get("active"):
        handler._json(409, {"error": "нет активной миссии"}); return
    body = _read_body(handler)
    amount = float(body.get("amount", 0))
    if amount <= 0:
        handler._json(400, {"error": "amount must be > 0"}); return
    data["costs"] = float(data.get("costs", 0)) + amount
    data["net"] = float(data.get("confirmed_income", 0)) - float(data["costs"])
    _write_mission(data)
    handler._json(200, {"ok": True, "mission": data})


def _complete(handler) -> None:
    data = _read_mission()
    if not data.get("active"):
        handler._json(409, {"error": "нет активной миссии"}); return
    body = _read_body(handler)
    try:
        verification = Verification.model_validate(body.get("verification") or {})
    except ValidationError as exc:
        handler._json(409, {
            "error": "миссия не может завершиться без валидной проверки",
            "status": "not_verified",
            "detail": exc.errors(include_url=False),
            "mission": data,
        }); return
    if verification.status is not VerificationStatus.VERIFIED:
        data["status"] = "not_verified"
        data["verification"] = verification.model_dump(mode="json")
        _write_mission(data)
        publish_event({"type": "mission.not_verified", "mission": data})
        handler._json(409, {
            "error": "результат миссии не подтверждён",
            "status": "not_verified",
            "mission": data,
        }); return
    data["active"] = False
    data["status"] = "verified"
    data["verification"] = verification.model_dump(mode="json")
    data["completed_at"] = time.time()
    data.setdefault("trace", []).append({
        "stage": "VERIFIED",
        "ts": time.time(),
        "summary": verification.reason,
        "evidence_ids": [item.id for item in verification.evidence],
    })
    _write_mission(data)
    publish_event({"type": "mission.verified", "mission": data})
    handler._json(200, {"ok": True, "mission": data})


registry.register("GET", "/api/mission/current", _current, "текущая миссия")
registry.register("POST", "/api/mission/start", _start, "старт миссии")
registry.register("POST", "/api/mission/step", _step, "обновить этап")
registry.register("POST", "/api/mission/complete", _complete, "завершить миссию")
registry.register("POST", "/api/mission/confirm_income", _confirm_income, "подтвердить доход")
registry.register("POST", "/api/mission/add_cost", _add_cost, "добавить затраты")
