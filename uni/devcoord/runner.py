from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from uni.devcoord.dispatcher import PreparedDispatch
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import WorkTaskState, WorkspaceEvent
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeManager, WorktreeSnapshot


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    task_id: str
    session_id: str
    pid: int
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class ProcessObservation:
    run_id: str
    running: bool
    exit_code: int | None
    snapshot: WorktreeSnapshot | None = None


@dataclass
class _RuntimeProcess:
    process: subprocess.Popen[str]
    stdout_handle: TextIO
    stderr_handle: TextIO
    prepared: PreparedDispatch
    run: AgentRun
    finished: ProcessObservation | None = None


class LocalAgentRunner:
    """Launch and supervise a prepared agent process inside its task worktree."""

    def __init__(
        self,
        store: WorkspaceStore,
        worktrees: WorktreeManager,
        *,
        logs_root: str | Path | None = None,
    ) -> None:
        self.store = store
        self.worktrees = worktrees
        self.sessions = AgentSessionManager(store)
        self.logs_root = Path(
            logs_root or (worktrees.repo_root / ".uni-dev" / "runs")
        ).resolve()
        self._runs: dict[str, _RuntimeProcess] = {}

    def start(self, prepared: PreparedDispatch, argv: list[str]) -> AgentRun:
        if not argv or not isinstance(argv[0], str) or not argv[0].strip():
            raise ValueError("argv must contain an executable")
        if not prepared.worktree.path.exists():
            raise FileNotFoundError(prepared.worktree.path)

        current = self.store.get_session(prepared.session.session_id)
        if current.task_id != prepared.task.id:
            raise RuntimeError("session is not bound to prepared task")
        if current.worktree_path != str(prepared.worktree.path):
            raise RuntimeError("session worktree does not match prepared dispatch")

        run_id = str(uuid4())
        log_dir = self.logs_root / prepared.task.id / run_id
        log_dir.mkdir(parents=True, exist_ok=False)
        stdout_path = log_dir / "stdout.log"
        stderr_path = log_dir / "stderr.log"
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                argv,
                cwd=prepared.worktree.path,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                shell=False,
            )
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            raise

        run = AgentRun(
            run_id=run_id,
            task_id=prepared.task.id,
            session_id=prepared.session.session_id,
            pid=process.pid,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        runtime = _RuntimeProcess(process, stdout_handle, stderr_handle, prepared, run)
        self._runs[run_id] = runtime
        self.sessions.attach_process(
            run.session_id,
            process_id=run.pid,
            stdout_log_path=str(run.stdout_path),
            stderr_log_path=str(run.stderr_path),
        )
        self._set_task_state(run.task_id, run.session_id, WorkTaskState.ACTIVE)
        self.store.append_event(
            WorkspaceEvent(
                event="runner.started",
                task_id=run.task_id,
                session_id=run.session_id,
                detail=f"pid={run.pid}",
            )
        )
        return run

    def tick(self, run_id: str, *, ttl_seconds: float = 600.0) -> ProcessObservation:
        runtime = self._runtime(run_id)
        if runtime.finished is not None:
            return runtime.finished
        exit_code = runtime.process.poll()
        if exit_code is None:
            self.sessions.heartbeat(runtime.run.session_id, ttl_seconds=ttl_seconds)
            return ProcessObservation(run_id=run_id, running=True, exit_code=None)
        return self._finalize(runtime, exit_code)

    def wait(self, run_id: str, *, timeout: float | None = None) -> ProcessObservation:
        runtime = self._runtime(run_id)
        if runtime.finished is not None:
            return runtime.finished
        exit_code = runtime.process.wait(timeout=timeout)
        return self._finalize(runtime, exit_code)

    def _runtime(self, run_id: str) -> _RuntimeProcess:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent run: {run_id}") from exc

    def _finalize(self, runtime: _RuntimeProcess, exit_code: int) -> ProcessObservation:
        if runtime.finished is not None:
            return runtime.finished
        runtime.stdout_handle.close()
        runtime.stderr_handle.close()
        snapshot = self.worktrees.snapshot(runtime.prepared.worktree)
        observation = f"process exited rc={exit_code}; head={snapshot.head_commit}"
        self._set_task_state(
            runtime.run.task_id,
            runtime.run.session_id,
            WorkTaskState.VERIFYING,
        )
        self.sessions.begin_verification(
            runtime.run.session_id,
            observation=observation,
        )
        self.store.append_event(
            WorkspaceEvent(
                event="runner.exited",
                task_id=runtime.run.task_id,
                session_id=runtime.run.session_id,
                detail=observation,
            )
        )
        finished = ProcessObservation(
            run_id=runtime.run.run_id,
            running=False,
            exit_code=exit_code,
            snapshot=snapshot,
        )
        runtime.finished = finished
        return finished

    def _set_task_state(
        self,
        task_id: str,
        session_id: str,
        state: WorkTaskState,
    ) -> None:
        current = self.store.get_workspace_task(task_id)
        if current.assigned_session_id != session_id:
            raise RuntimeError("task ownership changed during runner lifecycle")
        updated = current.model_copy(
            update={
                "state": state,
                "updated_at": utc_now(),
            }
        )
        self.store.save_workspace_task(updated)
