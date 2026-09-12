from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uni.devcoord.integration import (
    IntegrationManager,
    IntegrationVerificationError,
    UnownedChangeError,
)
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.workspace_models import (
    AccessMode,
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()

def _setup(tmp_path: Path, verification_argv: list[list[str]]):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mawc@example.invalid")
    _git(repo, "config", "user.name", "MAWC Test")
    (repo / "owned.txt").write_text("base", encoding="utf-8")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-qm", "base")

    worktrees = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    task_ref = worktrees.create("hermes", "UNI-500")
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(
        AgentSession(
            session_id="session-hermes",
            agent_id="hermes",
            display_name="Hermes",
            task_id="UNI-500",
            worktree_path=str(task_ref.path),
            state=SessionState.VERIFYING,
        )
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-500",
            title="Integrate me",
            state=WorkTaskState.VERIFIED,
            assigned_session_id="session-hermes",
            verification_argv=verification_argv,
        )
    )
    ResourceLeaseManager(store).claim(
        "UNI-500",
        "session-hermes",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="owned.txt")],
        ttl_seconds=600,
    )
    manager = IntegrationManager(
        repo,
        store,
        integration_path=tmp_path / "integration",
        candidates_root=tmp_path / "candidates",
    )
    return repo, store, task_ref, manager


def test_owned_verified_change_merges_and_releases_session(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "from pathlib import Path; assert Path('owned.txt').read_text() == 'changed'"]]
    repo, store, task_ref, manager = _setup(tmp_path, command)
    (task_ref.path / "owned.txt").write_text("changed", encoding="utf-8")

    outcome = manager.integrate("UNI-500")

    assert outcome.merged is True
    assert not outcome.candidate_path.exists()
    assert str(outcome.candidate_path) not in _git(repo, "worktree", "list", "--porcelain")
    assert store.get_workspace_task("UNI-500").state is WorkTaskState.MERGED
    session = store.get_session("session-hermes")
    assert session.state is SessionState.ACTIVE
    assert session.task_id is None
    assert session.worktree_path is None
    assert ResourceLeaseManager(store).list_active() == []
    assert (manager.integration_path / "owned.txt").read_text(encoding="utf-8") == "changed"
    assert _git(repo, "status", "--porcelain") == ""
    assert any(
        event.event == "integration.merged" and event.task_id == "UNI-500"
        for event in store.list_events(limit=30)
    )


def test_unowned_change_blocks_integration_and_keeps_ownership(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "pass"]]
    _, store, task_ref, manager = _setup(tmp_path, command)
    (task_ref.path / "owned.txt").write_text("changed", encoding="utf-8")
    (task_ref.path / "rogue.txt").write_text("rogue", encoding="utf-8")

    with pytest.raises(UnownedChangeError) as exc:
        manager.integrate("UNI-500")

    assert "rogue.txt" in exc.value.paths
    assert store.get_workspace_task("UNI-500").state is WorkTaskState.VERIFIED
    assert store.get_session("session-hermes").state is SessionState.VERIFYING
    assert ResourceLeaseManager(store).list_active()
    assert not manager.integration_path.exists()
    assert any(
        event.event == "integration.unowned_change"
        for event in store.list_events(limit=30)
    )


def test_post_merge_verification_failure_does_not_advance_integration(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "raise SystemExit(9)"]]
    _, store, task_ref, manager = _setup(tmp_path, command)
    (task_ref.path / "owned.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(IntegrationVerificationError):
        manager.integrate("UNI-500")

    assert store.get_workspace_task("UNI-500").state is WorkTaskState.VERIFIED
    assert store.get_session("session-hermes").state is SessionState.VERIFYING
    assert ResourceLeaseManager(store).list_active()
    assert (manager.integration_path / "owned.txt").read_text(encoding="utf-8") == "base"
    assert any(
        event.event == "integration.verification_failed"
        for event in store.list_events(limit=30)
    )


def test_exclusive_lease_counts_as_write_ownership(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "pass"]]
    _, store, task_ref, manager = _setup(tmp_path, command)
    leases = ResourceLeaseManager(store).list_active()
    assert len(leases) == 1
    ResourceLeaseManager(store).release(leases[0].lease_id)
    ResourceLeaseManager(store).claim(
        "UNI-500",
        "session-hermes",
        [ResourceRequest(
            resource_type=ResourceType.FILE,
            resource_key="owned.txt",
            access_mode=AccessMode.EXCLUSIVE,
        )],
    )
    (task_ref.path / "owned.txt").write_text("exclusive", encoding="utf-8")

    outcome = manager.integrate("UNI-500")

    assert outcome.merged is True
    assert (manager.integration_path / "owned.txt").read_text(encoding="utf-8") == "exclusive"


def test_merge_state_rolls_back_when_merged_event_write_fails(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "pass"]]
    _, store, task_ref, manager = _setup(tmp_path, command)
    (task_ref.path / "owned.txt").write_text("changed", encoding="utf-8")
    before_session = store.get_session("session-hermes")
    before_leases = ResourceLeaseManager(store).list_active()
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_integration_merged BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='integration.merged' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        manager.integrate("UNI-500")

    assert store.get_workspace_task("UNI-500").state is WorkTaskState.VERIFIED
    after_session = store.get_session("session-hermes")
    assert after_session.state is before_session.state
    assert after_session.task_id == before_session.task_id
    assert after_session.worktree_path == before_session.worktree_path
    after_leases = ResourceLeaseManager(store).list_active()
    assert [lease.lease_id for lease in after_leases] == [lease.lease_id for lease in before_leases]
    assert all(lease.state is before.state for lease, before in zip(after_leases, before_leases))
