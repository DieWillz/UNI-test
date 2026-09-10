from __future__ import annotations

import sqlite3
from pathlib import Path

from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceType,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_fresh_store_initializes_process_safe_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "coordination" / "workspace.sqlite"
    store = WorkspaceStore(db_path)

    assert db_path.exists()
    assert {"agent_sessions", "resource_leases", "workspace_events"} <= _tables(db_path)
    assert store.journal_mode().lower() == "wal"


def test_store_persists_session_and_audit_event(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = AgentSession(
        session_id="session-1",
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        state=SessionState.ACTIVE,
        capabilities=["python", "tests"],
    )

    store.save_session(session)
    loaded = store.get_session("session-1")

    assert loaded == session
    assert loaded.state is SessionState.ACTIVE

    event = WorkspaceEvent(
        event="session.registered",
        task_id="UNI-142",
        session_id="session-1",
        detail="Hermes registered",
    )
    store.append_event(event)

    events = store.list_events(limit=10)
    assert len(events) == 1
    assert events[0].event == "session.registered"
    assert events[0].session_id == "session-1"


def test_domain_models_expose_phase1_resource_vocabulary() -> None:
    from uni.devcoord.workspace_models import (
        AccessMode,
        LeaseState,
        ResourceLease,
        ResourceRequest,
    )

    request = ResourceRequest(
        resource_type=ResourceType.FILE,
        resource_key="uni/brain.py",
        access_mode=AccessMode.WRITE,
    )
    lease = ResourceLease(
        lease_id="lease-1",
        task_id="UNI-142",
        agent_session_id="session-1",
        resource_type=request.resource_type,
        resource_key=request.resource_key,
        access_mode=request.access_mode,
        state=LeaseState.CLAIMED,
    )

    assert request.resource_type.value == "file"
    assert lease.access_mode.value == "write"
    assert lease.state.value == "claimed"


def test_store_connections_enforce_foreign_keys(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    assert store.foreign_keys_enabled() is True
