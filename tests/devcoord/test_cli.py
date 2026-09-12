from __future__ import annotations

import json
from pathlib import Path

from uni.devcoord.__main__ import main
from uni.devcoord.workspace_models import AgentSession, WorkTaskState, WorkspaceTask
from uni.devcoord.workspace_store import WorkspaceStore


def _db(tmp_path: Path) -> Path:
    return tmp_path / "workspace.sqlite"


def test_cli_status_and_agents_use_workspace_store(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    store = WorkspaceStore(db)
    store.save_session(AgentSession(
        session_id="hermes-session", agent_id="hermes", display_name="Hermes",
    ))

    assert main(["agents", "--db", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["agent_id"] == "hermes"


def test_cli_status_can_inspect_task(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    store = WorkspaceStore(db)
    store.save_workspace_task(WorkspaceTask(
        id="UNI-CLI", title="CLI task", state=WorkTaskState.READY,
    ))

    assert main(["status", "--db", str(db)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tasks"][0]["id"] == "UNI-CLI"


def test_cli_pause_and_resume_agent(tmp_path: Path, capsys) -> None:
    db = _db(tmp_path)
    store = WorkspaceStore(db)
    store.save_session(AgentSession(
        session_id="codex-session", agent_id="codex", display_name="Codex",
    ))

    assert main(["pause-agent", "codex", "--db", str(db)]) == 0
    capsys.readouterr()
    assert store.get_session("codex-session").state.value == "stopped"

    assert main(["--db", str(db), "resume-agent", "codex"]) == 0
    capsys.readouterr()
    assert store.get_session("codex-session").state.value == "active"
