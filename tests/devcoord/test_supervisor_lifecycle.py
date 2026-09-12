from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from uni.devcoord.dispatcher import TaskDispatcher
from uni.devcoord.integration import IntegrationManager
from uni.devcoord.runner import LocalAgentRunner
from uni.devcoord.supervisor import AgentLaunchProfile, DevelopmentSupervisor
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


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mawc@example.invalid")
    _git(repo, "config", "user.name", "MAWC Test")
    (repo / "owned.txt").write_text("base", encoding="utf-8")
    _git(repo, "add", "owned.txt")
    _git(repo, "commit", "-qm", "base")
    return repo


def test_supervisor_verifies_integrates_then_dispatches_dependency(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    store.save_session(
        AgentSession(
            session_id="hermes-session",
            agent_id="hermes",
            display_name="Hermes",
            capabilities=["python"],
        )
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="TASK-A",
            title="First",
            priority=100,
            state=WorkTaskState.READY,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.FILE, resource_key="owned.txt")
            ],
            verification_argv=[[
                sys.executable,
                "-c",
                "from pathlib import Path; assert Path('owned.txt').read_text() == 'A'",
            ]],
        )
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="TASK-B",
            title="Dependent",
            priority=90,
            state=WorkTaskState.READY,
            dependencies=["TASK-A"],
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.FILE, resource_key="b.txt")
            ],
            verification_argv=[[
                sys.executable,
                "-c",
                "from pathlib import Path; assert Path('owned.txt').read_text() == 'A'; assert Path('b.txt').read_text() == 'B'",
            ]],
        )
    )

    worktrees = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    dispatcher = TaskDispatcher(store, worktrees)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "runs")
    verifier = VerificationManager(store)
    integration = IntegrationManager(
        repo,
        store,
        integration_path=tmp_path / "integration",
        candidates_root=tmp_path / "candidates",
    )

    script = (
        "import sys; from pathlib import Path; task=sys.argv[1]; "
        "Path('owned.txt').write_text('A') if task == 'TASK-A' else "
        "(assertion := None); "
        "Path('b.txt').write_text('B') if task == 'TASK-B' and Path('owned.txt').read_text() == 'A' else None"
    )
    supervisor = DevelopmentSupervisor(
        store,
        dispatcher,
        runner,
        profiles=[
            AgentLaunchProfile(
                agent_id="hermes",
                argv=[sys.executable, "-c", script, "{task_id}"],
            )
        ],
        verification_manager=verifier,
        integration_manager=integration,
    )

    first = supervisor.tick(ttl_seconds=600)
    assert [run.task_id for run in first.started_runs] == ["TASK-A"]

    time.sleep(0.25)
    second = supervisor.tick(ttl_seconds=600)
    assert store.get_workspace_task("TASK-A").state is WorkTaskState.MERGED
    assert [run.task_id for run in second.started_runs] == ["TASK-B"]

    time.sleep(0.25)
    third = supervisor.tick(ttl_seconds=600)
    assert store.get_workspace_task("TASK-B").state is WorkTaskState.MERGED
    session = store.get_session("hermes-session")
    assert session.task_id is None
    assert session.state.value == "active"
    assert third.started_runs == []
    assert (tmp_path / "integration" / "owned.txt").read_text(encoding="utf-8") == "A"
    assert (tmp_path / "integration" / "b.txt").read_text(encoding="utf-8") == "B"
    assert third.report is not None
    assert third.report.task_counts["merged"] == 2


def test_supervisor_marks_expired_session_stale_before_dispatch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.save_session(AgentSession(
        session_id="expired",
        agent_id="hermes",
        display_name="Hermes",
        capabilities=["python"],
        expires_at=expired_at,
    ))
    store.save_workspace_task(WorkspaceTask(
        id="TASK-EXPIRED",
        title="Must not dispatch",
        state=WorkTaskState.READY,
        required_capabilities=["python"],
    ))
    worktrees = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    supervisor = DevelopmentSupervisor(
        store,
        TaskDispatcher(store, worktrees),
        LocalAgentRunner(store, worktrees, logs_root=tmp_path / "runs"),
        profiles=[AgentLaunchProfile(agent_id="hermes", argv=[sys.executable, "-c", "pass"])],
    )

    tick = supervisor.tick(ttl_seconds=600)

    assert tick.started_runs == []
    assert store.get_session("expired").state is SessionState.STALE
    assert store.get_workspace_task("TASK-EXPIRED").state is WorkTaskState.READY
