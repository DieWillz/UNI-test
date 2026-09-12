from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.scheduler import TaskScheduler
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


def test_workspace_task_round_trip_preserves_dispatch_contract(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    task = WorkspaceTask(
        id="UNI-200",
        title="Build scheduler",
        priority=90,
        dependencies=["UNI-100"],
        required_capabilities=["python", "git"],
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="devcoord-scheduler"),
            ResourceRequest(resource_type=ResourceType.FILE, resource_key=r"uni\devcoord\scheduler.py"),
        ],
        state=WorkTaskState.READY,
    )
    store.save_workspace_task(task)
    loaded = store.get_workspace_task("UNI-200")
    listed = store.list_workspace_tasks()

    assert loaded.id == "UNI-200"
    assert loaded.dependencies == ["UNI-100"]
    assert loaded.required_capabilities == ["python", "git"]
    assert [item.resource_key for item in loaded.requested_resources] == [
        "devcoord-scheduler",
        r"uni\devcoord\scheduler.py",
    ]
    assert loaded.state is WorkTaskState.READY
    assert [item.id for item in listed] == ["UNI-200"]


def test_ready_tasks_respect_dependencies_capabilities_and_priority(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="agent-1",
        agent_id="hermes",
        display_name="Hermes",
        capabilities=["python", "git"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="BASE", title="Base", state=WorkTaskState.MERGED,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="HIGH", title="High", priority=100,
        dependencies=["BASE"], required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="VERIFIED_ONLY", title="Verified only", state=WorkTaskState.VERIFIED,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="WAITING_MERGE", title="Waiting merge", priority=150,
        dependencies=["VERIFIED_ONLY"], required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="BLOCKED", title="Blocked", priority=300,
        dependencies=["MISSING"], required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="WRONGCAP", title="Wrong cap", priority=250,
        required_capabilities=["cuda"], state=WorkTaskState.READY,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="LOW", title="Low", priority=10,
        required_capabilities=["git"], state=WorkTaskState.PLANNED,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="ACTIVE", title="Already running", priority=999,
        state=WorkTaskState.ACTIVE,
    ))

    ready = TaskScheduler(store).ready_tasks("agent-1")

    assert [task.id for task in ready] == ["HIGH", "LOW"]


def test_reserve_next_skips_conflict_and_claims_fallback(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="blocker", agent_id="codex", display_name="Codex",
        capabilities=["python"],
    ))
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    ResourceLeaseManager(store).claim(
        "OTHER",
        "blocker",
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="busy-logic")],
        ttl_seconds=600,
    )
    store.save_workspace_task(WorkspaceTask(
        id="PREFERRED", title="Preferred", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="busy-logic")
        ],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="FALLBACK", title="Fallback", priority=50,
        required_capabilities=["python"], state=WorkTaskState.READY,
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="free-logic")
        ],
    ))

    assignment = TaskScheduler(store).reserve_next("worker", ttl_seconds=600)

    assert assignment is not None
    assert assignment.task.id == "FALLBACK"
    assert store.get_workspace_task("PREFERRED").state is WorkTaskState.READY
    claimed = store.get_workspace_task("FALLBACK")
    assert claimed.state is WorkTaskState.CLAIMED
    assert claimed.assigned_session_id == "worker"
    assert any(lease.resource_key == "free-logic" for lease in assignment.leases)
    events = store.list_events(limit=10)
    assert any(event.event == "task.conflict" and event.task_id == "PREFERRED" for event in events)
    assert any(event.event == "task.claimed" and event.task_id == "FALLBACK" for event in events)


def test_two_processes_cannot_reserve_same_task(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace.sqlite"
    store = WorkspaceStore(db_path)
    for session_id in ("agent-a", "agent-b"):
        store.save_session(AgentSession(
            session_id=session_id,
            agent_id=session_id,
            display_name=session_id,
            capabilities=["python"],
        ))
    store.save_workspace_task(WorkspaceTask(
        id="ONLY", title="Only task", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    start_path = tmp_path / "start"
    code = """
import sys, time
from pathlib import Path
from uni.devcoord.scheduler import TaskScheduler
from uni.devcoord.workspace_store import WorkspaceStore

db_path, session_id, start_path, result_path = sys.argv[1:]
while not Path(start_path).exists():
    time.sleep(0.01)
assignment = TaskScheduler(WorkspaceStore(db_path)).reserve_next(session_id, ttl_seconds=600)
result = assignment.task.id if assignment else "none"
Path(result_path).write_text(result, encoding="utf-8")
"""
    result_paths = [tmp_path / "a.txt", tmp_path / "b.txt"]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(db_path), session_id, str(start_path), str(result_path)],
            cwd=str(Path(__file__).parents[2]),
        )
        for session_id, result_path in zip(("agent-a", "agent-b"), result_paths)
    ]
    start_path.write_text("go", encoding="utf-8")
    for process in processes:
        assert process.wait(timeout=15) == 0

    results = sorted(path.read_text(encoding="utf-8") for path in result_paths)
    assert results == ["ONLY", "none"]
    claimed = store.get_workspace_task("ONLY")
    assert claimed.state is WorkTaskState.CLAIMED
    assert claimed.assigned_session_id in {"agent-a", "agent-b"}
    task_leases = [
        lease for lease in ResourceLeaseManager(store).list_active()
        if lease.resource_type is ResourceType.GLOBAL and lease.resource_key == "task:only"
    ]
    assert len(task_leases) == 1


def test_reserve_next_rolls_back_task_when_claimed_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="ATOMIC", title="Atomic claim", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_task_claimed BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='task.claimed' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    try:
        TaskScheduler(store).reserve_next("worker", ttl_seconds=600)
        assert False, "claim event failure must propagate"
    except Exception as exc:
        assert "boom" in str(exc)

    task = store.get_workspace_task("ATOMIC")
    assert task.state is WorkTaskState.READY
    assert task.assigned_session_id is None
    assert ResourceLeaseManager(store).list_active() == []


def test_reserve_next_does_not_depend_on_compensating_release(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="ATOMIC-LEASE", title="Atomic lease", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_task_claimed_again BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='task.claimed' BEGIN SELECT RAISE(ABORT, 'claim-event-boom'); END"
        )
        conn.execute(
            "CREATE TRIGGER fail_compensating_release BEFORE UPDATE ON resource_leases "
            "WHEN NEW.state='released' BEGIN SELECT RAISE(ABORT, 'release-boom'); END"
        )

    try:
        TaskScheduler(store).reserve_next("worker", ttl_seconds=600)
        assert False, "claim event failure must propagate"
    except Exception as exc:
        assert "claim-event-boom" in str(exc)

    task = store.get_workspace_task("ATOMIC-LEASE")
    assert task.state is WorkTaskState.READY
    assert task.assigned_session_id is None
    assert ResourceLeaseManager(store).list_active() == []

def test_reserve_next_rechecks_session_state_inside_reservation(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="RACE", title="Session race", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    scheduler = TaskScheduler(store)
    original_ready = scheduler.ready_tasks

    def ready_then_stop(session_id: str):
        candidates = original_ready(session_id)
        current = store.get_session(session_id)
        store.save_session(current.model_copy(update={"state": SessionState.STOPPED}))
        return candidates

    scheduler.ready_tasks = ready_then_stop
    assignment = scheduler.reserve_next("worker", ttl_seconds=600)

    assert assignment is None
    assert store.get_workspace_task("RACE").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []

def test_reserve_next_rechecks_session_capabilities_inside_reservation(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="CAP-RACE", title="Capability race", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))
    scheduler = TaskScheduler(store)
    original_ready = scheduler.ready_tasks

    def ready_then_drop_capabilities(session_id: str):
        candidates = original_ready(session_id)
        current = store.get_session(session_id)
        store.save_session(current.model_copy(update={"capabilities": []}))
        return candidates

    scheduler.ready_tasks = ready_then_drop_capabilities
    assignment = scheduler.reserve_next("worker", ttl_seconds=600)

    assert assignment is None
    assert store.get_workspace_task("CAP-RACE").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []

def test_reserve_next_claims_resources_from_fresh_task_snapshot(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="RESOURCE-RACE", title="Resource race", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
        requested_resources=[
            ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="old-resource")
        ],
    ))
    scheduler = TaskScheduler(store)
    original_ready = scheduler.ready_tasks

    def ready_then_change_resources(session_id: str):
        candidates = original_ready(session_id)
        current = store.get_workspace_task("RESOURCE-RACE")
        store.save_workspace_task(current.model_copy(update={
            "requested_resources": [
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="new-resource")
            ]
        }))
        return candidates

    scheduler.ready_tasks = ready_then_change_resources
    assignment = scheduler.reserve_next("worker", ttl_seconds=600)

    assert assignment is not None
    assert {lease.resource_key for lease in assignment.leases} == {
        "task:resource-race", "new-resource"
    }


def test_busy_session_cannot_reserve_second_task(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(AgentSession(
        session_id="worker", agent_id="hermes", display_name="Hermes",
        task_id="ALREADY-BOUND", capabilities=["python"],
    ))
    store.save_workspace_task(WorkspaceTask(
        id="SECOND", title="Second task", priority=100,
        required_capabilities=["python"], state=WorkTaskState.READY,
    ))

    scheduler = TaskScheduler(store)

    assert scheduler.ready_tasks("worker") == []
    assert scheduler.reserve_next("worker", ttl_seconds=600) is None
    assert store.get_workspace_task("SECOND").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []
