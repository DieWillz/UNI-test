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
    assert verifying_session.process_id is None
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


def test_start_cleans_up_process_when_session_attach_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")

    class FakeProcess:
        pid = 424242

        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True
            return 0

    fake = FakeProcess()
    captured = {}

    def fake_popen(*args, **kwargs):
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]
        return fake

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with store.transaction(immediate=True) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_process_attach
            BEFORE UPDATE ON agent_sessions
            WHEN NEW.session_id = 'session-hermes'
            BEGIN
                SELECT RAISE(ABORT, 'attach failed');
            END;
            """
        )

    with pytest.raises(Exception, match="attach failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    assert fake.terminated is True
    assert fake.waited is True
    assert captured["stdout"].closed is True
    assert captured["stderr"].closed is True
    assert runner._runs == {}


def test_start_restores_session_when_post_attach_step_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    before = store.get_session(prepared.session.session_id)

    class FakeProcess:
        pid = 434343
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess())
    with store.transaction(immediate=True) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_task_activation
            BEFORE UPDATE ON workspace_tasks
            WHEN NEW.state = 'active'
            BEGIN
                SELECT RAISE(ABORT, 'state failed');
            END;
            """
        )

    with pytest.raises(Exception, match="state failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    restored = store.get_session(prepared.session.session_id)
    assert restored.process_id == before.process_id
    assert restored.stdout_log_path == before.stdout_log_path
    assert restored.stderr_log_path == before.stderr_log_path
    assert restored.last_observation == before.last_observation


def test_start_restores_task_state_when_runner_started_event_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    before_task = store.get_workspace_task(prepared.task.id)
    before_lease_states = [item.state for item in ResourceLeaseManager(store).list_active()]

    class FakeProcess:
        pid = 444444
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess())
    with store.transaction(immediate=True) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_runner_started_state_test
            BEFORE INSERT ON workspace_events
            WHEN NEW.event = 'runner.started'
            BEGIN
                SELECT RAISE(ABORT, 'event failed');
            END;
            """
        )

    with pytest.raises(Exception, match="event failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    restored_task = store.get_workspace_task(prepared.task.id)
    assert restored_task.state is before_task.state
    assert restored_task.updated_at == before_task.updated_at
    restored_lease_states = [item.state for item in ResourceLeaseManager(store).list_active()]
    assert restored_lease_states == before_lease_states


def test_start_cleanup_does_not_mask_original_error_when_terminate_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    before = store.get_session(prepared.session.session_id)

    class FakeProcess:
        pid = 454545
        def terminate(self):
            raise OSError("already gone")

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess())
    with store.transaction(immediate=True) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_process_attach_cleanup_test
            BEFORE UPDATE ON agent_sessions
            WHEN NEW.session_id = 'session-hermes'
            BEGIN
                SELECT RAISE(ABORT, 'attach failed');
            END;
            """
        )

    with pytest.raises(Exception, match="attach failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    restored = store.get_session(prepared.session.session_id)
    assert restored.process_id == before.process_id
    assert runner._runs == {}


def test_start_removes_empty_run_artifacts_when_popen_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    logs_root = tmp_path / "logs"
    runner = LocalAgentRunner(store, worktrees, logs_root=logs_root)

    def fail_popen(*args, **kwargs):
        raise OSError("launch failed")

    monkeypatch.setattr(subprocess, "Popen", fail_popen)

    with pytest.raises(OSError, match="launch failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    task_log_root = logs_root / prepared.task.id
    assert not task_log_root.exists() or list(task_log_root.iterdir()) == []
    assert runner._runs == {}


def test_start_rolls_back_lifecycle_events_when_runner_started_event_fails(tmp_path: Path) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    baseline_events = [event.event_id for event in store.list_events(limit=100)]

    class FakeProcess:
        pid = 464646
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess())
        with store.transaction(immediate=True) as conn:
            conn.execute(
                """
                CREATE TRIGGER fail_runner_started
                BEFORE INSERT ON workspace_events
                WHEN NEW.event = 'runner.started'
                BEGIN
                    SELECT RAISE(ABORT, 'runner started event failed');
                END;
                """
            )

        with pytest.raises(Exception, match="runner started event failed"):
            runner.start(prepared, [sys.executable, "-c", "pass"])
    finally:
        monkeypatch.undo()

    assert [event.event_id for event in store.list_events(limit=100)] == baseline_events


def test_finalize_rolls_back_verification_transition_when_exit_event_fails(tmp_path: Path) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    run = runner.start(prepared, [sys.executable, "-c", "print('done')"])

    with store.transaction(immediate=True) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_runner_exited
            BEFORE INSERT ON workspace_events
            WHEN NEW.event = 'runner.exited'
            BEGIN
                SELECT RAISE(ABORT, 'runner exited event failed');
            END;
            """
        )

    with pytest.raises(Exception, match="runner exited event failed"):
        runner.wait(run.run_id, timeout=5)

    assert store.get_workspace_task(prepared.task.id).state is WorkTaskState.ACTIVE
    assert store.get_session(prepared.session.session_id).state is SessionState.ACTIVE
    assert all(
        item.state is LeaseState.ACTIVE
        for item in ResourceLeaseManager(store).list_active()
    )


def test_finalize_records_exit_when_worktree_snapshot_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    run = runner.start(prepared, [sys.executable, "-c", "print('done')"])

    def fail_snapshot(_ref):
        raise OSError("git unavailable")

    monkeypatch.setattr(worktrees, "snapshot", fail_snapshot)

    finished = runner.wait(run.run_id, timeout=5)

    assert finished.running is False
    assert finished.exit_code == 0
    assert finished.snapshot is None
    assert store.get_workspace_task(prepared.task.id).state is WorkTaskState.VERIFYING
    assert store.get_session(prepared.session.session_id).state is SessionState.VERIFYING
    exited = store.list_events(limit=1)[0]
    assert exited.event == "runner.exited"
    assert "snapshot unavailable" in (exited.detail or "")


def test_start_removes_run_artifacts_when_lifecycle_commit_fails(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    logs_root = tmp_path / "logs"
    runner = LocalAgentRunner(store, worktrees, logs_root=logs_root)

    class FakeProcess:
        pid = 474747
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess())
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_lifecycle_commit BEFORE UPDATE ON agent_sessions "
            "BEGIN SELECT RAISE(ABORT, 'lifecycle failed'); END;"
        )

    with pytest.raises(Exception, match="lifecycle failed"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    task_log_root = logs_root / prepared.task.id
    assert not task_log_root.exists() or list(task_log_root.iterdir()) == []
    assert runner._runs == {}


def test_start_rejects_session_with_attached_process_before_launch(tmp_path: Path, monkeypatch) -> None:
    store, worktrees, prepared = _prepared(tmp_path)
    runner = LocalAgentRunner(store, worktrees, logs_root=tmp_path / "logs")
    current = store.get_session(prepared.session.session_id)
    store.save_session(current.model_copy(update={"process_id": 12345}))
    launched = False

    def unexpected_popen(*args, **kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("process launch must not happen")

    monkeypatch.setattr(subprocess, "Popen", unexpected_popen)

    with pytest.raises(RuntimeError, match="attached process"):
        runner.start(prepared, [sys.executable, "-c", "pass"])

    assert launched is False
    assert runner._runs == {}
