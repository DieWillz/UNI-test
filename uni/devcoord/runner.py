from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from uni.devcoord.dispatcher import PreparedDispatch
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import (
    AgentSession,
    LeaseState,
    ResourceLease,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
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
        if current.process_id is not None:
            raise RuntimeError("session already has an attached process")
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
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)
            try:
                log_dir.rmdir()
                log_dir.parent.rmdir()
            except OSError:
                pass
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
        try:
            self._commit_start_transition(run)
        except Exception:
            self._runs.pop(run_id, None)
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                stdout_handle.close()
                stderr_handle.close()
                stdout_path.unlink(missing_ok=True)
                stderr_path.unlink(missing_ok=True)
                try:
                    log_dir.rmdir()
                    log_dir.parent.rmdir()
                except OSError:
                    pass
            raise
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
        snapshot: WorktreeSnapshot | None = None
        try:
            snapshot = self.worktrees.snapshot(runtime.prepared.worktree)
            observation = f"process exited rc={exit_code}; head={snapshot.head_commit}"
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            observation = (
                f"process exited rc={exit_code}; snapshot unavailable: "
                f"{exc.__class__.__name__}: {detail}"
            )
        self._commit_verification_transition(
            runtime.run.task_id,
            runtime.run.session_id,
            observation,
        )
        finished = ProcessObservation(
            run_id=runtime.run.run_id,
            running=False,
            exit_code=exit_code,
            snapshot=snapshot,
        )
        runtime.finished = finished
        return finished


    def _commit_start_transition(self, run: AgentRun) -> None:
        with self.store.transaction(immediate=True) as conn:
            task_row = conn.execute(
                "SELECT payload_json FROM workspace_tasks WHERE task_id=?", (run.task_id,)
            ).fetchone()
            session_row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?", (run.session_id,)
            ).fetchone()
            if task_row is None or session_row is None:
                raise RuntimeError("runner lifecycle state disappeared during start")

            task = WorkspaceTask.model_validate(json.loads(task_row[0]))
            session = AgentSession.model_validate(json.loads(session_row[0]))
            if task.assigned_session_id != run.session_id or session.task_id != run.task_id:
                raise RuntimeError("runner lifecycle ownership changed during start")
            if session.state is SessionState.STALE:
                raise RuntimeError("stale session requires controlled takeover")
            if session.process_id is not None:
                raise RuntimeError("session already has an attached process")

            attached = session.model_copy(
                update={
                    "process_id": run.pid,
                    "stdout_log_path": str(run.stdout_path),
                    "stderr_log_path": str(run.stderr_path),
                    "state": SessionState.ACTIVE,
                    "last_observation": f"process started pid={run.pid}",
                }
            )
            active_task = task.model_copy(
                update={"state": WorkTaskState.ACTIVE, "updated_at": utc_now()}
            )
            self.store.save_session(attached, conn=conn)
            self.store.save_workspace_task(active_task, conn=conn)

            lease_rows = conn.execute(
                "SELECT payload_json FROM resource_leases "
                "WHERE agent_session_id=? AND state!=?",
                (run.session_id, LeaseState.RELEASED.value),
            ).fetchall()
            for row in lease_rows:
                lease = ResourceLease.model_validate(json.loads(row[0])).model_copy(
                    update={"state": LeaseState.ACTIVE}
                )
                self.store.save_resource_lease(lease, conn=conn)

            for event in (
                WorkspaceEvent(
                    event="session.process_attached", task_id=run.task_id,
                    session_id=run.session_id, detail=f"pid={run.pid}",
                ),
                WorkspaceEvent(
                    event="runner.started", task_id=run.task_id,
                    session_id=run.session_id, detail=f"pid={run.pid}",
                ),
            ):
                self.store.append_event(event, conn=conn)

    def _commit_verification_transition(
        self, task_id: str, session_id: str, observation: str
    ) -> None:
        with self.store.transaction(immediate=True) as conn:
            task_row = conn.execute(
                "SELECT payload_json FROM workspace_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            session_row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if task_row is None or session_row is None:
                raise RuntimeError("runner lifecycle state disappeared during finalize")

            task = WorkspaceTask.model_validate(json.loads(task_row[0]))
            session = AgentSession.model_validate(json.loads(session_row[0]))
            if task.assigned_session_id != session_id or session.task_id != task_id:
                raise RuntimeError("runner lifecycle ownership changed during finalize")

            now = utc_now()
            verifying_task = task.model_copy(
                update={"state": WorkTaskState.VERIFYING, "updated_at": now}
            )
            verifying_session = session.model_copy(
                update={
                    "state": SessionState.VERIFYING,
                    "process_id": None,
                    "last_observation": observation[:4000],
                }
            )
            self.store.save_workspace_task(verifying_task, conn=conn)
            self.store.save_session(verifying_session, conn=conn)

            lease_rows = conn.execute(
                "SELECT payload_json FROM resource_leases "
                "WHERE agent_session_id=? AND state!=?",
                (session_id, LeaseState.RELEASED.value),
            ).fetchall()
            for row in lease_rows:
                lease = ResourceLease.model_validate(json.loads(row[0])).model_copy(
                    update={"state": LeaseState.VERIFYING}
                )
                self.store.save_resource_lease(lease, conn=conn)

            for event in (
                WorkspaceEvent(
                    event="session.verifying", task_id=task_id, session_id=session_id,
                    detail=observation[:4000],
                ),
                WorkspaceEvent(
                    event="runner.exited", task_id=task_id, session_id=session_id,
                    detail=observation,
                ),
            ):
                self.store.append_event(event, conn=conn)
