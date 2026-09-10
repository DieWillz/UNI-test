from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import (
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


@dataclass(frozen=True)
class VerificationCommandResult:
    argv: tuple[str, ...]
    return_code: int | None
    stdout: str
    stderr: str
    error: str = ""


@dataclass(frozen=True)
class VerificationOutcome:
    task_id: str
    passed: bool
    commands: list[VerificationCommandResult]
    detail: str = ""

class VerificationManager:
    """Run explicit verification commands inside the task worktree."""

    def __init__(
        self,
        store: WorkspaceStore,
        *,
        timeout_seconds: float = 300.0,
        output_limit: int = 4000,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if output_limit <= 0:
            raise ValueError("output_limit must be positive")
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.output_limit = output_limit

    def verify(self, task_id: str) -> VerificationOutcome:
        task = self.store.get_workspace_task(task_id)
        if task.state is not WorkTaskState.VERIFYING:
            raise RuntimeError("task must be VERIFYING before verification")
        if not task.assigned_session_id:
            raise RuntimeError("verifying task has no assigned session")

        session = self.store.get_session(task.assigned_session_id)
        if session.state is not SessionState.VERIFYING:
            raise RuntimeError("assigned session must be VERIFYING")
        if not session.worktree_path:
            raise RuntimeError("verifying session has no worktree")
        worktree = Path(session.worktree_path)
        if not worktree.exists():
            raise FileNotFoundError(worktree)

        if not task.verification_argv:
            detail = "no verification commands configured"
            self._finish(task_id, WorkTaskState.FAILED, detail)
            self.store.append_event(
                WorkspaceEvent(
                    event="verification.failed",
                    task_id=task_id,
                    session_id=session.session_id,
                    detail=detail,
                )
            )
            return VerificationOutcome(task_id, False, [], detail)

        results: list[VerificationCommandResult] = []
        for argv in task.verification_argv:
            result = self._run_command(argv, worktree)
            results.append(result)
            self._record_command(task_id, session.session_id, result)
            if result.return_code != 0:
                detail = self._failure_detail(result)
                self._finish(task_id, WorkTaskState.FAILED, detail)
                self.store.append_event(
                    WorkspaceEvent(
                        event="verification.failed",
                        task_id=task_id,
                        session_id=session.session_id,
                        detail=detail,
                    )
                )
                return VerificationOutcome(task_id, False, results, detail)

        detail = f"{len(results)} verification command(s) passed"
        self._finish(task_id, WorkTaskState.VERIFIED, detail)
        self.store.append_event(
            WorkspaceEvent(
                event="verification.passed",
                task_id=task_id,
                session_id=session.session_id,
                detail=detail,
            )
        )
        return VerificationOutcome(task_id, True, results, detail)

    def _run_command(
        self,
        argv: list[str],
        worktree: Path,
    ) -> VerificationCommandResult:
        if not argv or not isinstance(argv[0], str) or not argv[0].strip():
            return VerificationCommandResult(tuple(argv), None, "", "", "invalid argv")
        try:
            completed = subprocess.run(
                argv,
                cwd=worktree,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return VerificationCommandResult(
                tuple(argv),
                None,
                self._clip(exc.stdout or ""),
                self._clip(exc.stderr or ""),
                f"timeout after {self.timeout_seconds}s",
            )
        except OSError as exc:
            return VerificationCommandResult(
                tuple(argv), None, "", "", f"{type(exc).__name__}: {exc}"
            )
        return VerificationCommandResult(
            tuple(argv),
            completed.returncode,
            self._clip(completed.stdout),
            self._clip(completed.stderr),
        )

    def _clip(self, value: str) -> str:
        return value[-self.output_limit :]

    def _record_command(
        self,
        task_id: str,
        session_id: str,
        result: VerificationCommandResult,
    ) -> None:
        detail = (
            f"argv={list(result.argv)!r}; rc={result.return_code}; "
            f"error={result.error!r}; stdout={result.stdout!r}; stderr={result.stderr!r}"
        )[:4000]
        self.store.append_event(
            WorkspaceEvent(
                event="verification.command",
                task_id=task_id,
                session_id=session_id,
                detail=detail,
            )
        )

    def _failure_detail(self, result: VerificationCommandResult) -> str:
        if result.error:
            return result.error[:4000]
        return f"verification command failed rc={result.return_code}"[:4000]

    def _finish(self, task_id: str, state: WorkTaskState, detail: str) -> None:
        current = self.store.get_workspace_task(task_id)
        updated = current.model_copy(
            update={"state": state, "updated_at": utc_now()}
        )
        self.store.save_workspace_task(updated)
