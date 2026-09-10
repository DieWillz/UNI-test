from __future__ import annotations

from pathlib import Path

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_status import WorkspaceStatus
from uni.devcoord.workspace_store import WorkspaceStore


def _session(session_id: str, state: SessionState) -> AgentSession:
    return AgentSession(
        session_id=session_id,
        agent_id=session_id,
        display_name=session_id,
        task_id=f"task-{session_id}",
        state=state,
    )


def test_summary_reports_objective_counts(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(_session("active", SessionState.ACTIVE))
    store.save_session(_session("stale", SessionState.STALE))
    ResourceLeaseManager(store).claim(
        "task-active",
        "active",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni\\brain.py")],
        ttl_seconds=600,
    )
    store.append_event(WorkspaceEvent(event="lease.conflict", session_id="stale"))
    store.append_event(
        WorkspaceEvent(event="workspace.unowned_change", resource_key="uni/agent.py")
    )

    summary = WorkspaceStatus(store).summary()

    assert summary.active_sessions == 1
    assert summary.stale_sessions == 1
    assert summary.active_leases == 1
    assert summary.conflict_events == 1
    assert summary.unowned_changes == 1


def test_resource_lookup_normalizes_file_key(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(_session("active", SessionState.ACTIVE))
    ResourceLeaseManager(store).claim(
        "task-active",
        "active",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni\\brain.py")],
        ttl_seconds=600,
    )
    matches = WorkspaceStatus(store).resource(ResourceType.FILE, "./uni/brain.py")

    assert len(matches) == 1
    assert matches[0].resource_key == "uni/brain.py"


def test_events_are_newest_first_and_limited(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.append_event(WorkspaceEvent(event="first"))
    store.append_event(WorkspaceEvent(event="second"))

    events = WorkspaceStatus(store).events(limit=1)

    assert [event.event for event in events] == ["second"]