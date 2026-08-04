#!/usr/bin/env python3
"""UNI Control Panel — local web GUI for tasks and monitoring."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent  # artifacts/ or repo root when placed there
STATE_DIR = ROOT / "data"
STATE_FILE = STATE_DIR / "panel_state.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Try to locate a UNI checkout (GitHub layout or local)
CANDIDATE_ROOTS = [
    WORKSPACE,
    WORKSPACE / "UNI-test",
    WORKSPACE / "UNI",
    Path.cwd(),
    Path.cwd().parent,
]


def find_workspace() -> Path:
    for base in CANDIDATE_ROOTS:
        if (base / "uni" / "devcoord").is_dir() or (base / ".uni-dev").is_dir():
            return base
        if (base / "scripts" / "uni_dev_coordinator.py").is_file():
            return base
    return WORKSPACE


WS = find_workspace()
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))

# ---------------------------------------------------------------------------
# Optional devcoord bridge
# ---------------------------------------------------------------------------

DEVCOORD_OK = False
_coordinator = None


def try_devcoord():
    global DEVCOORD_OK, _coordinator
    try:
        from uni.devcoord.config import load_development_config
        from uni.devcoord.coordinator import DevelopmentCoordinator
        from uni.devcoord.providers import ProviderRegistry
        from uni.devcoord.store import CoordinationStore

        cfg_path = WS / ".uni-dev" / "coordination" / "providers.example.yaml"
        if not cfg_path.is_file():
            cfg_path = WS / ".uni-dev" / "coordination" / "providers.yaml"
        if not cfg_path.is_file():
            DEVCOORD_OK = False
            return None
        config = load_development_config(cfg_path)
        state_path = (WS / config.state_path).resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _coordinator = DevelopmentCoordinator(
            WS,
            CoordinationStore(state_path),
            ProviderRegistry(config.providers, allow_paid_api=config.allow_paid_api),
        )
        DEVCOORD_OK = True
        return _coordinator
    except Exception as exc:  # noqa: BLE001
        DEVCOORD_OK = False
        _coordinator = None
        print(f"[panel] devcoord unavailable: {exc}")
        return None


# ---------------------------------------------------------------------------
# Local fallback store (when devcoord missing)
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_local() -> dict[str, Any]:
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"tasks": [], "events": [], "notes": []}


def save_local(data: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=2000)
    instructions: str = Field(default="", max_length=4000)
    providers: str = Field(default="local_lm_studio", max_length=200)
    files: str = Field(default="", description="Comma-separated relative paths")
    expected_output: str = Field(default="Structured result / review")


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="UNI Control Panel", version="1.0")
static_dir = ROOT / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def _startup() -> None:
    try_devcoord()
    print(f"[panel] workspace={WS}")
    print(f"[panel] devcoord={'ON' if DEVCOORD_OK else 'OFF (local store)'}")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_path = static_dir / "index.html"
    if not html_path.is_file():
        return HTMLResponse("<h1>UNI Panel</h1><p>static/index.html missing</p>", status_code=500)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    if DEVCOORD_OK and _coordinator is not None:
        try:
            for p in _coordinator.providers.providers:  # type: ignore[attr-defined]
                providers.append(
                    {
                        "id": getattr(p, "id", str(p)),
                        "enabled": getattr(p, "enabled", True),
                        "transport": getattr(p, "transport", "?"),
                    }
                )
        except Exception:  # noqa: BLE001
            providers = [{"id": "local_lm_studio", "enabled": True, "transport": "api"}]
    else:
        providers = [{"id": "local_fallback", "enabled": True, "transport": "local"}]

    return {
        "ok": True,
        "workspace": str(WS),
        "devcoord": DEVCOORD_OK,
        "time": _now(),
        "providers": providers,
        "manifest_hint": "UNI MANIFESTO v2.5 Accepted",
    }


@app.get("/api/tasks")
def api_tasks() -> dict[str, Any]:
    if DEVCOORD_OK and _coordinator is not None:
        try:
            tasks = []
            for t in _coordinator.store.list_tasks():
                d = t.model_dump(mode="json") if hasattr(t, "model_dump") else dict(t)
                tasks.append(d)
            return {"source": "devcoord", "tasks": tasks}
        except Exception as exc:  # noqa: BLE001
            return {"source": "error", "tasks": [], "error": str(exc)}
    data = load_local()
    return {"source": "local", "tasks": data.get("tasks", [])}


@app.post("/api/tasks")
def api_create_task(body: TaskCreate) -> dict[str, Any]:
    file_list = [f.strip() for f in body.files.split(",") if f.strip()]
    provider_list = [p.strip() for p in body.providers.split(",") if p.strip()]

    if DEVCOORD_OK and _coordinator is not None:
        try:
            from uni.devcoord.models import DevelopmentTask

            task = DevelopmentTask(
                title=body.title,
                goal=body.goal,
                instructions=body.instructions or body.goal,
                provider_sequence=provider_list,
                artifact_paths=file_list,
                expected_output=body.expected_output,
            )
            _coordinator.create_task(task)
            return {"ok": True, "source": "devcoord", "task": task.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    data = load_local()
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": body.title,
        "goal": body.goal,
        "instructions": body.instructions or body.goal,
        "provider_sequence": provider_list,
        "artifact_paths": file_list,
        "expected_output": body.expected_output,
        "status": "pending",
        "created_at": _now(),
        "results": [],
    }
    data.setdefault("tasks", []).insert(0, task)
    data.setdefault("events", []).append(
        {"ts": _now(), "type": "task_created", "task_id": task["id"], "title": task["title"]}
    )
    save_local(data)
    return {"ok": True, "source": "local", "task": task}


@app.post("/api/tasks/{task_id}/run")
async def api_run_task(task_id: str) -> dict[str, Any]:
    if DEVCOORD_OK and _coordinator is not None:
        try:
            task = await _coordinator.run_all(task_id)
            return {"ok": True, "source": "devcoord", "task": task.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    data = load_local()
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "done_local"
            t["results"] = t.get("results") or []
            t["results"].append(
                {
                    "provider": "local_fallback",
                    "text": (
                        "Devcoord не подключён. Задача сохранена локально. "
                        "Положи панель в корень UNI-test (рядом с uni/devcoord) "
                        "и перезапусти — run пойдёт через координатор."
                    ),
                    "at": _now(),
                }
            )
            save_local(data)
            return {"ok": True, "source": "local", "task": t}
    raise HTTPException(status_code=404, detail="task not found")


@app.get("/api/tasks/{task_id}")
def api_show_task(task_id: str) -> dict[str, Any]:
    if DEVCOORD_OK and _coordinator is not None:
        try:
            task = _coordinator.store.get_task(task_id)
            payload = task.model_dump(mode="json")
            payload["events"] = [
                e.model_dump(mode="json") for e in _coordinator.store.events_for(task.id)
            ]
            return {"ok": True, "source": "devcoord", "task": payload}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    data = load_local()
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return {"ok": True, "source": "local", "task": t}
    raise HTTPException(status_code=404, detail="task not found")


@app.get("/api/events")
def api_events() -> dict[str, Any]:
    if DEVCOORD_OK and _coordinator is not None:
        try:
            # best-effort: collect from all tasks
            events = []
            for t in _coordinator.store.list_tasks():
                for e in _coordinator.store.events_for(t.id):
                    events.append(e.model_dump(mode="json"))
            events = events[-100:]
            return {"source": "devcoord", "events": events}
        except Exception:  # noqa: BLE001
            pass
    data = load_local()
    return {"source": "local", "events": data.get("events", [])[-100:]}


@app.post("/api/notes")
def api_notes(body: NoteCreate) -> dict[str, Any]:
    data = load_local()
    note = {"id": str(uuid.uuid4())[:8], "text": body.text, "at": _now()}
    data.setdefault("notes", []).insert(0, note)
    save_local(data)
    return {"ok": True, "note": note}


@app.get("/api/notes")
def api_list_notes() -> dict[str, Any]:
    data = load_local()
    return {"notes": data.get("notes", [])[:50]}


def main() -> None:
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8787, reload=False)


if __name__ == "__main__":
    main()
