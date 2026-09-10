from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uni.devcoord.dispatcher import TaskDispatcher
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.runner import LocalAgentRunner
from uni.devcoord.workspace_models import (
    LeaseState,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


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


def _prepared(tmp_path: Path):
    repo = _make_repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    session = AgentSessionManager(store).register(
        agent_id="hermes",
        display_name="Hermes",
        session_id="session-hermes",
        capabilities=["python"],
        ttl_seconds=1,
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-400",
            title="Run agent",
            priority=100,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="runner-test")
            ],
            state=WorkTaskState.READY,
        )
    )
    worktrees = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    prepared = TaskDispatcher(store, worktrees).prepare(session.session_id)
    assert prepared is not None
    return store, worktrees, prepared


def test_start_and_tick_use_task_worktree_and_refresh_ttl(tmp_path: Path) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    before = store.get_session(prepared.session.session_id)
    code = (
        "import os,time; "
        "open('agent-cwd.txt','w',encoding='utf-8').write(os.getcwd()); "
        "print('runner-hello', flush=True); time.sleep(1.5)"
    )
    run = runner.start(prepared, [sys.executable, "-c", code])
    running = runner.tick(run.run_id, ttl_seconds=600)

    refreshed = store.get_session(prepared.session.session_id)
    active_leases = ResourceLeaseManager(store).list_active()
    assert running.running is True
    assert refreshed.process_id == run.pid
    assert refreshed.expires_at > before.expires_at
    assert refreshed.stdout_log_path == str(run.stdout_path)
    assert refreshed.stderr_log_path == str(run.stderr_path)
    assert all(item.state is LeaseState.ACTIVE for item in active_leases)

    finished = runner.wait(run.run_id, timeout=5)
    assert finished.running is False
    assert finished.exit_code == 0
    assert finished.snapshot is not None
    assert Path(prepared.worktree.path / "agent-cwd.txt").read_text(encoding="utf-8") == str(
        prepared.worktree.path
    )
    assert "runner-hello" in run.stdout_path.read_text(encoding="utf-8")

    verifying_session = store.get_session(prepared.session.session_id)
    verifying_task = store.get_workspace_task(prepared.task.id)
    verifying_leases = ResourceLeaseManager(store).list_active()
    assert verifying_session.state is SessionState.VERIFYING
    assert verifying_task.state is WorkTaskState.VERIFYING
    assert all(item.state is LeaseState.VERIFYING for item in verifying_leases)
    assert store.list_events(limit=1)[0].event == "runner.exited"


def test_exit_zero_is_not_verified_and_leases_remain_blocking(tmp_path: Path) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    run = runner.start(prepared, [sys.executable, "-c", "print('done')"])

    observed = runner.wait(run.run_id, timeout=5)

    assert observed.exit_code == 0
    assert store.get_workspace_task(prepared.task.id).state is WorkTaskState.VERIFYING
    assert ResourceLeaseManager(store).list_active()
    assert all(
        item.state is LeaseState.VERIFYING
        for item in ResourceLeaseManager(store).list_active()
    )


def test_empty_argv_is_rejected_before_process_launch(tmp_path: Path) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")

    with pytest.raises(ValueError, match="argv"):
        runner.start(prepared, [])

    current = store.get_session(prepared.session.session_id)
    assert current.process_id is None
    assert current.state is SessionState.ACTIVE
