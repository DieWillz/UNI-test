from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from uni.devcoord.dispatcher import TaskDispatcher
from uni.devcoord.runner import LocalAgentRunner
from uni.devcoord.supervisor import AgentLaunchProfile, DevelopmentSupervisor
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
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
    (repo / "base.txt").write_text("base", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-qm", "base")
    return repo


def test_supervisor_dispatches_then_stops_reassignment_while_verifying(tmp_path: Path) -> None:
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
            id="UNI-300",
            title="Primary",
            priority=100,
            state=WorkTaskState.READY,
            required_capabilities=["python"],
            requested_resources=[
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="phase6")
            ],
        )
    )
    store.save_workspace_task(
        WorkspaceTask(
            id="UNI-301",
            title="Fallback",
            priority=10,
            state=WorkTaskState.READY,
            required_capabilities=["python"],
        )
    )

    worktrees = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    dispatcher = TaskDispatcher(store, worktrees)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "runs")
    script = (
        "import time; from pathlib import Path; "
        "Path('worker-cwd.txt').write_text(str(Path.cwd()), encoding='utf-8'); "
        "time.sleep(0.15)"
    )
    supervisor = DevelopmentSupervisor(
        store,
        dispatcher,
        runner,
        profiles=[
            AgentLaunchProfile(agent_id="hermes", argv=[sys.executable, "-c", script])
        ],
    )

    first = supervisor.tick(ttl_seconds=600)
    assert len(first.started_runs) == 1
    assert first.started_runs[0].task_id == "UNI-300"
    assert store.get_workspace_task("UNI-300").state is WorkTaskState.ACTIVE

    time.sleep(0.3)
    second = supervisor.tick(ttl_seconds=600)
    assert second.finished_runs[0].task_id == "UNI-300"
    assert store.get_workspace_task("UNI-300").state is WorkTaskState.VERIFYING
    session = store.get_session("hermes-session")
    assert session.state.value == "verifying"
    assert session.worktree_path
    cwd_file = Path(session.worktree_path) / "worker-cwd.txt"
    assert Path(cwd_file.read_text(encoding="utf-8")).resolve() == Path(
        session.worktree_path
    ).resolve()

    third = supervisor.tick(ttl_seconds=600)
    assert third.started_runs == []
    assert store.get_workspace_task("UNI-301").state is WorkTaskState.READY
    assert third.report.task_counts["verifying"] == 1
    assert third.report.task_counts["ready"] == 1
