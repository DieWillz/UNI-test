from __future__ import annotations

from pathlib import Path

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.reporter import DevelopmentReporter
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


def test_reporter_uses_persisted_objective_counts(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(
        AgentSession(
            session_id="free",
            agent_id="hermes",
            display_name="Hermes",
            state=SessionState.ACTIVE,
        )
    )
    store.save_session(
        AgentSession(
            session_id="verifying",
            agent_id="codex",
            display_name="Codex",
            task_id="UNI-2",
            state=SessionState.VERIFYING,
        )
    )
    store.save_workspace_task(
        WorkspaceTask(id="UNI-1", title="Ready", state=WorkTaskState.READY)
    )
    store.save_workspace_task(
        WorkspaceTask(id="UNI-2", title="Verify", state=WorkTaskState.VERIFYING)
    )
    store.save_workspace_task(
        WorkspaceTask(id="UNI-3", title="Done", state=WorkTaskState.VERIFIED)
    )
    store.save_workspace_task(
        WorkspaceTask(id="UNI-4", title="Blocked", state=WorkTaskState.BLOCKED)
    )
    store.append_event(WorkspaceEvent(event="task.conflict", task_id="UNI-1"))
    store.append_event(
        WorkspaceEvent(event="workspace.unowned_change", resource_key="uni/brain.py")
    )

    report = DevelopmentReporter(store).snapshot()

    assert report.session_counts == {"active": 1, "verifying": 1}
    assert report.task_counts["ready"] == 1
    assert report.task_counts["verifying"] == 1
    assert report.task_counts["verified"] == 1
    assert report.task_counts["blocked"] == 1
    assert report.conflict_events == 1
    assert report.unowned_changes == 1


def test_workspace_store_lists_sessions_for_supervisor(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(
        AgentSession(session_id="b", agent_id="codex", display_name="Codex")
    )
    store.save_session(
        AgentSession(session_id="a", agent_id="hermes", display_name="Hermes")
    )

    sessions = store.list_sessions()

    assert [session.session_id for session in sessions] == ["b", "a"]


def test_reporter_classifies_expired_runtime_state_as_stale(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="expired", agent_id="expired", display_name="Expired",
        state=SessionState.ACTIVE,
        expires_at="2000-01-01T00:00:00+00:00",
    ))
    ResourceLeaseManager(store).claim(
        "TASK", "expired",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/expired.py")],
        ttl_seconds=600,
    )
    lease = ResourceLeaseManager(store).list_active()[0]
    store.save_resource_lease(lease.model_copy(update={
        "expires_at": "2000-01-01T00:00:00+00:00"
    }))

    report = DevelopmentReporter(store).snapshot()

    assert report.session_counts.get("active", 0) == 0
    assert report.session_counts["stale"] == 1
    assert report.lease_counts.get("claimed", 0) == 0
    assert report.lease_counts["stale"] == 1
