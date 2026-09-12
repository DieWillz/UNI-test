from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from uni.devcoord.dispatcher import TaskDispatcher
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.workspace_models import (
    ResourceRequest,
    ResourceType,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeCollisionError, WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mawc@example.invalid")
    _git(repo, "config", "user.name", "MAWC Test")
    (repo / "base.txt").write_text("committed", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-qm", "base")
    return repo


def _register(store: WorkspaceStore, session_id: str, agent_id: str = "hermes"):
    return AgentSessionManager(store).register(
        agent_id=agent_id,
        display_name=agent_id,
        session_id=session_id,
        capabilities=["python"],
        ttl_seconds=600,
    )


def test_prepare_binds_reserved_task_worktree_and_session(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = _register(store, "session-hermes")
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-300",
            title="Dispatcher",
            priority=100,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="dispatcher")
            ],
            state=WorkTaskState.READY,
        )
    )
    dispatcher = TaskDispatcher(
        store,
        WorktreeManager(repo, worktrees_root=tmp_path / "worktrees"),
    )

    prepared = dispatcher.prepare(session.session_id)

    assert prepared is not None
    assert prepared.task.id == "UNI-300"
    assert prepared.worktree.path.exists()
    bound = store.get_session(session.session_id)
    claimed = store.get_workspace_task("UNI-300")
    assert bound.task_id == "UNI-300"
    assert bound.worktree_path == str(prepared.worktree.path)
    assert claimed.state is WorkTaskState.CLAIMED
    assert claimed.assigned_session_id == session.session_id
    assert store.list_events(limit=1)[0].event == "dispatch.prepared"


def test_prepare_without_runnable_task_has_no_side_effects(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = _register(store, "session-hermes")
    dispatcher = TaskDispatcher(
        store,
        WorktreeManager(repo, worktrees_root=tmp_path / "worktrees"),
    )

    assert dispatcher.prepare(session.session_id) is None

    unchanged = store.get_session(session.session_id)
    assert unchanged.task_id is None
    assert unchanged.worktree_path is None
    assert not (tmp_path / "worktrees").exists()


def test_worktree_failure_rolls_back_only_its_reservation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = _register(store, "session-hermes", "hermes")
    other = _register(store, "session-codex", "codex")
    leases = ResourceLeaseManager(store)
    unrelated = leases.claim(
        "UNI-other",
        other.session_id,
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="other-logic")],
        ttl_seconds=600,
    )[0]
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-301",
            title="Collision",
            priority=100,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="dispatcher")
            ],
            state=WorkTaskState.READY,
        )
    )
    worktrees_root = tmp_path / "worktrees"
    collision = worktrees_root / "hermes" / "UNI-301"
    collision.mkdir(parents=True)
    dispatcher = TaskDispatcher(store, WorktreeManager(repo, worktrees_root=worktrees_root))

    with pytest.raises(WorktreeCollisionError):
        dispatcher.prepare(session.session_id)

    rolled_back = store.get_workspace_task("UNI-301")
    unchanged = store.get_session(session.session_id)
    active = ResourceLeaseManager(store).list_active()
    assert rolled_back.state is WorkTaskState.READY
    assert rolled_back.assigned_session_id is None
    assert unchanged.task_id is None
    assert unchanged.worktree_path is None
    assert [item.lease_id for item in active] == [unrelated.lease_id]
    assert store.list_events(limit=1)[0].event == "dispatch.failed"


def test_prepare_db_failure_removes_worktree_and_rolls_back_reservation(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = _register(store, "session-hermes")
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-302",
            title="Atomic dispatch",
            priority=100,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="dispatcher")
            ],
            state=WorkTaskState.READY,
        )
    )
    worktrees_root = tmp_path / "worktrees"
    dispatcher = TaskDispatcher(store, WorktreeManager(repo, worktrees_root=worktrees_root))
    with store.connection() as conn:
        conn.execute(
            "CREATE TRIGGER fail_dispatch_prepared BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='dispatch.prepared' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        dispatcher.prepare(session.session_id)

    task = store.get_workspace_task("UNI-302")
    unchanged = store.get_session(session.session_id)
    assert task.state is WorkTaskState.READY
    assert task.assigned_session_id is None
    assert unchanged.task_id is None
    assert unchanged.worktree_path is None
    assert ResourceLeaseManager(store).list_active() == []
    assert not (worktrees_root / "hermes" / "UNI-302").exists()
    assert _git(repo, "branch", "--list", "mawc/hermes/UNI-302") == ""
    assert store.list_events(limit=1)[0].event == "dispatch.failed"
