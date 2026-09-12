from __future__ import annotations

from pathlib import Path

import pytest

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.service import DevelopmentCoordinatorService
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


def _service(tmp_path: Path) -> tuple[WorkspaceStore, DevelopmentCoordinatorService]:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    return store, DevelopmentCoordinatorService(store)


def test_status_and_file_owner_are_backed_by_live_store(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="hermes-session", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="UNI-1", title="Core", state=WorkTaskState.READY,
    ))
    lease = ResourceLeaseManager(store).claim(
        "UNI-1", "hermes-session",
        [ResourceRequest(resource_type=ResourceType.TREE, resource_key="uni/devcoord")],
    )[0]

    status = service.development_status()
    owner = service.inspect_file_owner("uni/devcoord/models.py")

    assert status["summary"]["active_sessions"] == 1
    assert status["tasks"][0]["id"] == "UNI-1"
    assert status["leases"][0]["lease_id"] == lease.lease_id
    assert owner["owned"] is True
    assert owner["owners"][0]["agent_id"] == "hermes"


def test_pause_and_resume_agent_persist_state_and_events(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="codex-session", agent_id="codex", display_name="Codex",
    ))

    paused = service.pause_agent("codex")
    resumed = service.resume_agent("codex")

    assert paused.state is SessionState.STOPPED
    assert resumed.state is SessionState.ACTIVE
    events = [event.event for event in store.list_events(limit=10)]
    assert "agent.paused" in events
    assert "agent.resumed" in events


def test_stale_agent_cannot_be_resumed_without_takeover(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="stale-session", agent_id="hermes", display_name="Hermes",
        state=SessionState.STALE,
    ))

    with pytest.raises(RuntimeError, match="takeover"):
        service.resume_agent("hermes")


def test_task_controls_update_priority_and_pause_state(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_workspace_task(WorkspaceTask(
        id="UNI-2", title="Task", priority=5, state=WorkTaskState.READY,
    ))

    prioritized = service.prioritize_task("UNI-2", 90)
    paused = service.pause_task("UNI-2")
    resumed = service.resume_task("UNI-2")

    assert prioritized.priority == 90
    assert paused.state is WorkTaskState.BLOCKED
    assert resumed.state is WorkTaskState.READY
    events = [event.event for event in store.list_events(limit=20)]
    assert "task.prioritized" in events
    assert "task.paused" in events
    assert "task.resumed" in events


def test_release_lease_control_releases_requested_lease(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="session", agent_id="agent", display_name="Agent",
    ))
    lease = ResourceLeaseManager(store).claim(
        "TASK", "session",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
    )[0]

    released = service.release_lease(lease.lease_id)

    assert released.state.value == "released"
    assert ResourceLeaseManager(store).list_active() == []


def test_list_and_inspect_methods_return_persisted_entities(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="hermes-session", agent_id="hermes", display_name="Hermes",
    ))
    store.save_workspace_task(WorkspaceTask(
        id="UNI-3", title="Inspect me", state=WorkTaskState.READY,
    ))

    assert service.list_agents()[0]["agent_id"] == "hermes"
    assert service.list_tasks()[0]["id"] == "UNI-3"
    assert service.inspect_agent("hermes")["session"]["session_id"] == "hermes-session"
    assert service.inspect_task("UNI-3")["task"]["title"] == "Inspect me"
    assert service.list_conflicts() == []


def test_assign_specific_task_claims_resources_atomically(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="worker", agent_id="codex", display_name="Codex",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="UNI-4", title="Specific", state=WorkTaskState.READY,
        required_capabilities=["python"],
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="service-api")
        ],
    ))

    result = service.assign_task("UNI-4", "worker")

    assert result["task"]["state"] == WorkTaskState.CLAIMED.value
    assert result["task"]["assigned_session_id"] == "worker"
    assert {item["resource_key"] for item in result["leases"]} == {
        "task:uni-4", "service-api"
    }


def test_assign_next_and_heartbeat_delegate_to_existing_runtime(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="UNI-5", title="Next", state=WorkTaskState.READY,
        required_capabilities=["python"],
    ))

    assignment = service.assign_next("worker")
    before = store.get_session("worker")
    refreshed = service.heartbeat("worker", ttl_seconds=900)

    assert assignment is not None
    assert assignment["task"]["id"] == "UNI-5"
    assert refreshed.expires_at is not None
    assert refreshed.heartbeat_at >= before.heartbeat_at


def test_can_write_and_audit_paths_are_exposed_by_service(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="owner", agent_id="hermes", display_name="Hermes",
    ))
    ResourceLeaseManager(store).claim(
        "TASK", "owner",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
    )

    decision = service.can_write("hermes", "uni/brain.py")
    findings = service.audit_paths(["uni/free.py"])

    assert decision["decision"] == "ALLOW"
    assert findings[0]["event"] == "workspace.unowned_change"
def test_release_lease_rolls_back_when_audit_event_fails(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="session", agent_id="agent", display_name="Agent",
    ))
    lease = ResourceLeaseManager(store).claim(
        "TASK", "session",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
    )[0]
    with store.connection() as conn:
        conn.execute(
            "CREATE TRIGGER fail_lease_released BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='lease.released' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        service.release_lease(lease.lease_id)

    active = ResourceLeaseManager(store).list_active()
    assert [item.lease_id for item in active] == [lease.lease_id]
    assert store.list_events(limit=20) == []

def test_pause_agent_rejects_busy_session(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="busy", agent_id="hermes", display_name="Hermes",
        task_id="UNI-BUSY", process_id=4242,
    ))

    with pytest.raises(RuntimeError, match="idle"):
        service.pause_agent("busy")

    assert store.get_session("busy").state is SessionState.ACTIVE
    assert store.list_events(limit=20) == []


def test_pause_task_rejects_claimed_task(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_workspace_task(WorkspaceTask(
        id="UNI-CLAIMED", title="Busy task", state=WorkTaskState.CLAIMED,
        assigned_session_id="worker",
    ))

    with pytest.raises(RuntimeError, match="queued"):
        service.pause_task("UNI-CLAIMED")

    assert store.get_workspace_task("UNI-CLAIMED").state is WorkTaskState.CLAIMED
    assert store.list_events(limit=20) == []



def test_stop_agent_stops_only_idle_session(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="idle", agent_id="hermes", display_name="Hermes",
    ))

    stopped = service.stop_agent("hermes")

    assert stopped.state is SessionState.STOPPED
    assert store.list_events(limit=1)[0].event == "agent.stopped"


def test_force_takeover_requires_stale_session_and_snapshot(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    session = AgentSession(
        session_id="stale", agent_id="hermes", display_name="Hermes",
        task_id="TASK-STALE", state=SessionState.STALE,
    )
    store.save_session(session)

    record = service.force_takeover("stale", "checkpoint/stale.json")

    assert record["stale_session_id"] == "stale"
    assert store.get_session("stale").state is SessionState.STOPPED
    assert store.list_events(limit=1)[0].event == "takeover.prepared"

def test_reassign_claimed_task_moves_idle_ownership(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    for session_id in ("old", "new"):
        store.save_session(AgentSession(
            session_id=session_id, agent_id=session_id, display_name=session_id,
            capabilities=["python"],
        ))
    store.save_workspace_task(WorkspaceTask(
        id="MOVE", title="Move me", state=WorkTaskState.READY,
        required_capabilities=["python"],
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/move.py")
        ],
    ))
    service.assign_task("MOVE", "old")

    moved = service.reassign_task("MOVE", "new")

    assert moved["task"]["assigned_session_id"] == "new"
    assert moved["task"]["state"] == WorkTaskState.CLAIMED.value
    assert {lease["agent_session_id"] for lease in moved["leases"]} == {"new"}
    events = [event.event for event in store.list_events(limit=20)]
    assert "task.reassigned" in events


def test_reassign_rejects_busy_target_without_releasing_source(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="old", agent_id="old", display_name="old",
        capabilities=["python"],
    ))
    store.save_session(AgentSession(
        session_id="busy", agent_id="busy", display_name="busy",
        task_id="OTHER", capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="MOVE", title="Move me", state=WorkTaskState.READY,
        required_capabilities=["python"],
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/move.py")
        ],
    ))
    assigned = service.assign_task("MOVE", "old")
    original_ids = {item["lease_id"] for item in assigned["leases"]}

    with pytest.raises(RuntimeError, match="idle|busy|task"):
        service.reassign_task("MOVE", "busy")

    assert store.get_workspace_task("MOVE").assigned_session_id == "old"
    assert {item.lease_id for item in ResourceLeaseManager(store).list_active()} == original_ids


def test_assign_task_is_atomic_when_assignment_event_fails(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="worker", agent_id="worker", display_name="worker",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="ATOMIC-ASSIGN", title="Atomic assign", state=WorkTaskState.READY,
        required_capabilities=["python"],
    ))
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_assignment_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='task.assigned' BEGIN SELECT RAISE(ABORT, 'assign-boom'); END"
        )
        conn.execute(
            "CREATE TRIGGER fail_compensating_release BEFORE UPDATE ON resource_leases "
            "WHEN NEW.state='released' BEGIN SELECT RAISE(ABORT, 'release-boom'); END"
        )

    with pytest.raises(Exception, match="assign-boom"):
        service.assign_task("ATOMIC-ASSIGN", "worker")

    task = store.get_workspace_task("ATOMIC-ASSIGN")
    assert task.state is WorkTaskState.READY
    assert task.assigned_session_id is None
    assert ResourceLeaseManager(store).list_active() == []


def test_resume_agent_refreshes_expired_heartbeat_window(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.save_session(AgentSession(
        session_id="paused", agent_id="paused", display_name="Paused",
        state=SessionState.STOPPED,
        heartbeat_at="2000-01-01T00:00:00+00:00",
        expires_at="2000-01-01T00:01:00+00:00",
    ))

    resumed = service.resume_agent("paused")
    summary = service.development_status()["summary"]

    assert resumed.state is SessionState.ACTIVE
    assert resumed.heartbeat_at > "2000-01-01T00:00:00+00:00"
    assert resumed.expires_at > resumed.heartbeat_at
    assert summary["active_sessions"] == 1
    assert summary["stale_sessions"] == 0
