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
        id="BASE", title="Base", state=WorkTaskState.VERIFIED,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="HIGH", title="High", priority=100,
        dependencies=["BASE"], required_capabilities=["python"], state=WorkTaskState.READY,
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
