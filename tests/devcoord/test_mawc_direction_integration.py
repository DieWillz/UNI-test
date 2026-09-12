from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from uni.direction_sync import SyncCheck
from uni.devcoord.dispatcher import TaskDispatcher
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.scheduler import TaskScheduler
from uni.devcoord.service import DevelopmentCoordinatorService
from uni.devcoord.workspace_models import (
    AcceptanceItem,
    AgentSession,
    ResourceRequest,
    ResourceType,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeManager
from uni.devcoord.direction_gate import MawcDirectionCoordinator


class FakeDirectionGate:
    def __init__(self) -> None:
        self.revision = "rev-1"
        self.acks: dict[str, str] = {}
        self.conflict_paths: dict[str, str] = {}
    def acknowledge(self, agent: str) -> dict[str, str]:
        self.acks[agent] = self.revision
        return {
            "revision": self.revision,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        }

    def check(self, agent: str, *, paths=()) -> SyncCheck:
        ack = self.acks.get(agent)
        if ack is None:
            return SyncCheck(False, "not_acknowledged", self.revision)
        if ack != self.revision:
            return SyncCheck(False, "stale_direction", self.revision)
        conflicts = [
            {"path": path, "owner": self.conflict_paths[path], "task": "foreign"}
            for path in paths if path in self.conflict_paths
        ]
        if conflicts:
            return SyncCheck(False, "ownership_conflict", self.revision, conflicts)
        return SyncCheck(True, "current", self.revision)


def _store(tmp_path: Path) -> WorkspaceStore:
    return WorkspaceStore(tmp_path / "workspace.sqlite")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "mawc@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "MAWC Test"], cwd=repo, check=True)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def _register(store: WorkspaceStore, session_id: str, display_name: str) -> AgentSession:
    return AgentSessionManager(store).register(
        agent_id=session_id,
        display_name=display_name,
        session_id=session_id,
        capabilities=["python"],
        ttl_seconds=600,
    )


def _task(task_id: str, resource: str | None = None) -> WorkspaceTask:
    requested = []
    if resource:
        requested.append(
            ResourceRequest(resource_type=ResourceType.FILE, resource_key=resource)
        )
    return WorkspaceTask(
        id=task_id,
        title=task_id,
        required_capabilities=["python"],
        requested_resources=requested,
        state=WorkTaskState.READY,
    )


def test_stale_agent_does_not_receive_new_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    gate.revision = "rev-2"
    store.save_workspace_task(_task("T1"))

    assert TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id) is None
    assert store.get_workspace_task("T1").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []
    assert sync.snapshot()["agents"][0]["status"] == "STALE"


def test_synced_agent_receives_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    store.save_workspace_task(_task("T1"))

    assignment = TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id)

    assert assignment is not None
    assert assignment.task.id == "T1"


def test_two_agents_cannot_receive_same_exclusive_resource(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    a = _register(store, "agent-a", "Agent A")
    b = _register(store, "agent-b", "Agent B")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(a.session_id)
    sync.acknowledge(b.session_id)
    store.save_workspace_task(_task("T1", "uni/shared.py"))
    store.save_workspace_task(_task("T2", "uni/shared.py"))

    first = TaskScheduler(store, direction_sync=sync).reserve_next(a.session_id)
    second = TaskScheduler(store, direction_sync=sync).reserve_next(b.session_id)

    assert first is not None
    assert second is None
    shared = [
        lease for lease in ResourceLeaseManager(store).list_active()
        if lease.resource_key == "uni/shared.py"
    ]
    assert len(shared) == 1


def test_heartbeat_updates_last_updated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = _register(store, "agent-a", "Agent A")
    before = session.heartbeat_at
    refreshed = AgentSessionManager(store).heartbeat(session.session_id, ttl_seconds=600)

    state = MawcDirectionCoordinator(store, FakeDirectionGate()).snapshot()
    agent = state["agents"][0]
    assert refreshed.heartbeat_at != before
    assert agent["last_updated"] == refreshed.heartbeat_at
    assert state["updated_at"] >= refreshed.heartbeat_at


def test_lost_heartbeat_is_visible_as_stale_without_releasing_lease(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = _register(store, "agent-a", "Agent A")
    lease = ResourceLeaseManager(store).claim(
        "T1",
        session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/live.py")],
        ttl_seconds=600,
    )[0]
    expired = session.model_copy(update={
        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    })
    store.save_session(expired)
    AgentSessionManager(store).mark_stale(now=datetime.now(timezone.utc))

    state = MawcDirectionCoordinator(store, FakeDirectionGate()).snapshot()
    assert state["agents"][0]["stale"] is True
    assert state["agents"][0]["status"] == "STALE"
    remaining = ResourceLeaseManager(store).list_active()
    assert [item.lease_id for item in remaining] == [lease.lease_id]
    assert remaining[0].state.value == "stale"


def test_revision_change_requires_resync(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    gate.revision = "rev-2"
    store.save_workspace_task(_task("T1"))

    assert TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id) is None
    sync.acknowledge(session.session_id)
    assignment = TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id)

    assert assignment is not None
    assert assignment.task.id == "T1"


def test_revision_change_does_not_silently_destroy_current_lease(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    store.save_workspace_task(_task("T1", "uni/live.py"))
    assignment = TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id)
    assert assignment is not None

    gate.revision = "rev-2"
    decision = sync.refresh(session.session_id)

    assert decision.stale is True
    active = ResourceLeaseManager(store).list_active()
    assert {lease.lease_id for lease in active} == {
        lease.lease_id for lease in assignment.leases
    }
    assert all(lease.state.value != "released" for lease in active)


def test_progress_is_computed_from_acceptance_items(tmp_path: Path) -> None:
    store = _store(tmp_path)
    items = [
        AcceptanceItem(key=f"a-{index}", passed=index < 5)
        for index in range(7)
    ]
    store.save_workspace_task(WorkspaceTask(
        id="T1",
        title="Progress",
        state=WorkTaskState.READY,
        acceptance_items=items,
    ))

    progress = MawcDirectionCoordinator(store, FakeDirectionGate()).snapshot()["progress"]["T1"]

    assert progress["passed"] == 5
    assert progress["total"] == 7
    assert progress["percent"] == 71
    assert progress["owner_verified"] is False
    assert progress["user_confirmed_percent"] == 71


def test_dispatcher_enforces_direction_sync_before_worktree_creation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    gate.revision = "rev-2"
    store.save_workspace_task(_task("T1"))

    dispatcher = TaskDispatcher(
        store,
        WorktreeManager(repo, worktrees_root=tmp_path / "worktrees"),
        direction_sync=sync,
    )

    assert dispatcher.prepare(session.session_id) is None
    assert store.get_workspace_task("T1").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []
    assert not (tmp_path / "worktrees").exists()


def test_service_assign_next_enforces_direction_sync(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    gate.revision = "rev-2"
    store.save_workspace_task(_task("T1"))

    service = DevelopmentCoordinatorService(store, direction_sync=sync)

    assert service.assign_next(session.session_id) is None
    assert store.get_workspace_task("T1").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []


def test_service_assign_task_enforces_direction_sync(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    gate.revision = "rev-2"
    store.save_workspace_task(_task("T1"))
    service = DevelopmentCoordinatorService(store, direction_sync=sync)

    try:
        service.assign_task("T1", session.session_id)
        assert False, "stale direction must block direct assignment"
    except RuntimeError as exc:
        assert "eligible" in str(exc)

    assert store.get_workspace_task("T1").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []


def test_snapshot_exposes_mawc_data_contract(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(session.session_id)
    store.save_workspace_task(_task("T1", "uni/a.py"))

    state = sync.snapshot()

    assert {"agents", "tasks", "assignments", "leases", "progress", "updated_at",
            "direction_revision", "ack_revision", "stale", "blockers"} <= set(state)
    agent = state["agents"][0]
    assert {
        "direction_revision_ack", "direction_synced_at", "last_heartbeat",
        "current_task", "progress", "owned_paths", "status", "stale", "blockers",
    } <= set(agent)


def test_service_reassign_blocks_stale_target_without_releasing_source_lease(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    source = _register(store, "agent-a", "Agent A")
    target = _register(store, "agent-b", "Agent B")
    sync = MawcDirectionCoordinator(store, gate)
    sync.acknowledge(source.session_id)
    sync.acknowledge(target.session_id)
    store.save_workspace_task(_task("T1", "uni/live.py"))
    original = TaskScheduler(store, direction_sync=sync).reserve_next(source.session_id)
    assert original is not None
    original_ids = {item.lease_id for item in original.leases}
    gate.revision = "rev-2"

    service = DevelopmentCoordinatorService(store, direction_sync=sync)
    try:
        service.reassign_task("T1", target.session_id)
        assert False, "stale target must not receive reassigned work"
    except RuntimeError as exc:
        assert "direction" in str(exc).lower() or "eligible" in str(exc).lower()

    task = store.get_workspace_task("T1")
    assert task.assigned_session_id == source.session_id
    assert {item.lease_id for item in ResourceLeaseManager(store).list_active()} == original_ids


def test_service_can_acknowledge_direction_through_mawc(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    service = DevelopmentCoordinatorService(store, direction_sync=sync)

    acknowledged = service.acknowledge_direction(session.session_id)

    assert acknowledged.direction_revision_ack == "rev-1"
    assert acknowledged.direction_synced_at is not None
    assert sync.snapshot()["agents"][0]["status"] == "READY"


def test_cli_service_wires_project_direction_sync(tmp_path: Path) -> None:
    from uni.devcoord.__main__ import _service

    db = tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite"
    service = _service(str(db), repo_root=tmp_path)

    assert service.direction_sync is not None


def test_cli_parser_exposes_direction_ack_command() -> None:
    from uni.devcoord.__main__ import _build_parser

    args = _build_parser().parse_args(["ack-direction", "session-a"])
    assert args.command == "ack-direction"
    assert args.session_id == "session-a"


def test_expired_heartbeat_blocks_new_work_without_manual_stale_sweep(tmp_path: Path) -> None:
    store = _store(tmp_path)
    gate = FakeDirectionGate()
    session = _register(store, "agent-a", "Agent A")
    sync = MawcDirectionCoordinator(store, gate)
    session = sync.acknowledge(session.session_id)
    store.save_session(session.model_copy(update={
        "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    }))
    store.save_workspace_task(_task("T1"))

    state = sync.snapshot()
    assignment = TaskScheduler(store, direction_sync=sync).reserve_next(session.session_id)

    assert state["agents"][0]["status"] == "STALE"
    assert state["agents"][0]["stale"] is True
    assert assignment is None
    assert store.get_workspace_task("T1").state is WorkTaskState.READY
    assert ResourceLeaseManager(store).list_active() == []
