from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.verification import VerificationManager
from uni.devcoord.workspace_models import (
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


def _setup(
    tmp_path: Path,
    verification_argv: list[list[str]],
) -> tuple[WorkspaceStore, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mawc@example.invalid")
    _git(repo, "config", "user.name", "MAWC Test")
    (repo / "base.txt").write_text("base", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-qm", "base")
    worktree = WorktreeManager(
        repo, worktrees_root=tmp_path / "worktrees"
    ).create("hermes", "UNI-400")
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(
        AgentSession(
            session_id="session-hermes",
            agent_id="hermes",
            display_name="Hermes",
            task_id="UNI-400",
            worktree_path=str(worktree.path),
            state=SessionState.VERIFYING,
        )
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-400",
            title="Verify me",
            state=WorkTaskState.VERIFYING,
            assigned_session_id="session-hermes",
            verification_argv=verification_argv,
        )
    )
    ResourceLeaseManager(store).claim(
        "UNI-400",
        "session-hermes",
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="verify-test")],
        ttl_seconds=600,
    )
    return store, worktree.path


def test_successful_explicit_verification_marks_task_verified(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "from pathlib import Path; Path('cwd.txt').write_text(str(Path.cwd()), encoding='utf-8')"]]
    store, worktree = _setup(tmp_path, command)

    outcome = VerificationManager(store).verify("UNI-400")
    assert outcome.passed is True
    assert [item.return_code for item in outcome.commands] == [0]
    assert store.get_workspace_task("UNI-400").state is WorkTaskState.VERIFIED
    assert store.get_session("session-hermes").state is SessionState.VERIFYING
    assert Path(worktree / "cwd.txt").read_text(encoding="utf-8") == str(worktree)
    assert ResourceLeaseManager(store).list_active()
    assert any(
        event.event == "verification.passed" and event.task_id == "UNI-400"
        for event in store.list_events(limit=20)
    )


def test_failing_verification_marks_task_failed_with_evidence(tmp_path: Path) -> None:
    command = [[sys.executable, "-c", "import sys; print('evidence-out'); print('evidence-err', file=sys.stderr); raise SystemExit(7)"]]
    store, _ = _setup(tmp_path, command)

    outcome = VerificationManager(store).verify("UNI-400")

    assert outcome.passed is False
    assert outcome.commands[-1].return_code == 7
    assert "evidence-out" in outcome.commands[-1].stdout
    assert "evidence-err" in outcome.commands[-1].stderr
    assert store.get_workspace_task("UNI-400").state is WorkTaskState.FAILED
    assert ResourceLeaseManager(store).list_active()


def test_empty_verification_config_fails_closed(tmp_path: Path) -> None:
    store, _ = _setup(tmp_path, [])

    outcome = VerificationManager(store).verify("UNI-400")

    assert outcome.passed is False
    assert outcome.commands == []
    assert store.get_workspace_task("UNI-400").state is WorkTaskState.FAILED
    assert any(
        event.event == "verification.failed" and "no verification commands" in event.detail
        for event in store.list_events(limit=20)
    )


def test_only_verifying_tasks_can_enter_verification(tmp_path: Path) -> None:
    store, _ = _setup(tmp_path, [[sys.executable, "-c", "pass"]])
    task = store.get_workspace_task("UNI-400")
    store.save_workspace_task(task.model_copy(update={"state": WorkTaskState.ACTIVE}))

    with pytest.raises(RuntimeError, match="VERIFYING"):
        VerificationManager(store).verify("UNI-400")
