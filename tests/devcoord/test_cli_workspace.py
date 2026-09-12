from __future__ import annotations

import json
from pathlib import Path

from uni.devcoord.__main__ import main
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "workspace.sqlite"
    store = WorkspaceStore(path)
    store.save_session(
        AgentSession(session_id="hermes", agent_id="hermes", display_name="Hermes")
    )
    store.save_workspace_task(
        WorkspaceTask(id="TASK-1", title="CLI task", state=WorkTaskState.READY, priority=10)
    )
    return path


def _json_output(capsys) -> dict | list:
    return json.loads(capsys.readouterr().out)


def test_status_prints_live_workspace_json(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["status", "--db", str(db)]) == 0
    payload = _json_output(capsys)
    assert payload["summary"]["active_sessions"] == 1
    assert payload["tasks"][0]["id"] == "TASK-1"


def test_agents_and_tasks_are_queryable(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["agents", "--db", str(db)]) == 0
    assert _json_output(capsys)[0]["agent_id"] == "hermes"
    assert main(["tasks", "--db", str(db)]) == 0
    assert _json_output(capsys)[0]["id"] == "TASK-1"


def test_owner_controls_round_trip(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["pause-agent", "hermes", "--db", str(db)]) == 0
    assert _json_output(capsys)["state"] == "stopped"
    assert main(["resume-agent", "hermes", "--db", str(db)]) == 0
    assert _json_output(capsys)["state"] == "active"
    assert main(["prioritize-task", "TASK-1", "900", "--db", str(db)]) == 0
    assert _json_output(capsys)["priority"] == 900
    assert main(["pause-task", "TASK-1", "--db", str(db)]) == 0
    assert _json_output(capsys)["state"] == "blocked"
    assert main(["resume-task", "TASK-1", "--db", str(db)]) == 0
    assert _json_output(capsys)["state"] == "ready"


def test_file_owner_reports_unowned_path(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["file-owner", "uni/free.py", "--db", str(db)]) == 0
    payload = _json_output(capsys)
    assert payload == {"path": "uni/free.py", "owned": False, "owners": []}


def test_unknown_workspace_object_returns_nonzero(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["pause-agent", "missing", "--db", str(db)]) == 2
    payload = _json_output(capsys)
    assert payload["error"]


def test_assignment_inspection_and_heartbeat_commands(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["assign-task", "TASK-1", "hermes", "--db", str(db)]) == 0
    assigned = _json_output(capsys)
    assert assigned["task"]["assigned_session_id"] == "hermes"

    assert main(["inspect-agent", "hermes", "--db", str(db)]) == 0
    assert _json_output(capsys)["session"]["session_id"] == "hermes"
    assert main(["inspect-task", "TASK-1", "--db", str(db)]) == 0
    assert _json_output(capsys)["task"]["state"] == "claimed"

    assert main(["heartbeat", "hermes", "--ttl", "900", "--db", str(db)]) == 0
    assert _json_output(capsys)["expires_at"] is not None


def test_guard_audit_and_release_commands(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    assert main(["can-write", "hermes", "uni/free.py", "--db", str(db)]) == 0
    assert _json_output(capsys)["decision"] == "ALLOW_WITH_WARNING"

    assert main(["audit", "uni/free.py", "--db", str(db)]) == 0
    findings = _json_output(capsys)
    assert findings[0]["event"] == "workspace.unowned_change"

    assert main(["assign-task", "TASK-1", "hermes", "--db", str(db)]) == 0
    assignment = _json_output(capsys)
    lease_id = assignment["leases"][0]["lease_id"]
    assert main(["release-lease", lease_id, "--db", str(db)]) == 0
    assert _json_output(capsys)["state"] == "released"


def test_stop_takeover_and_reassign_commands(tmp_path: Path, capsys) -> None:
    db = tmp_path / "workspace.sqlite"
    store = WorkspaceStore(db)
    store.save_session(AgentSession(
        session_id="idle", agent_id="idle", display_name="Idle",
    ))
    assert main(["stop-agent", "idle", "--db", str(db)]) == 0
    assert '"stopped"' in capsys.readouterr().out

    store.save_session(AgentSession(
        session_id="stale", agent_id="stale", display_name="Stale",
        state=SessionState.STALE,
    ))
    assert main([
        "force-takeover", "stale", "checkpoint/stale.json", "--db", str(db)
    ]) == 0
    assert "takeover_id" in capsys.readouterr().out
    for session_id in ("old", "new"):
        store.save_session(AgentSession(
            session_id=session_id, agent_id=session_id, display_name=session_id,
            capabilities=["python"],
        ))
    store.save_workspace_task(WorkspaceTask(
        id="MOVE", title="Move", state=WorkTaskState.READY,
        required_capabilities=["python"],
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/move.py")
        ],
    ))
    assert main(["assign-task", "MOVE", "old", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["reassign-task", "MOVE", "new", "--db", str(db)]) == 0
    payload = _json_output(capsys)
    assert payload["task"]["assigned_session_id"] == "new"
