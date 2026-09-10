from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from uni.devcoord.lease_rules import resources_overlap
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import (
    AccessMode,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


class UnownedChangeError(RuntimeError):
    def __init__(self, paths: list[str]) -> None:
        self.paths = paths
        super().__init__("unowned changed paths: " + ", ".join(paths))


class IntegrationVerificationError(RuntimeError):
    pass

@dataclass(frozen=True)
class IntegrationOutcome:
    task_id: str
    merged: bool
    task_commit: str
    integration_commit: str
    candidate_path: Path


class IntegrationManager:
    def __init__(
        self,
        repo_root: str | Path,
        store: WorkspaceStore,
        *,
        integration_path: str | Path,
        candidates_root: str | Path,
        integration_branch: str = "mawc/integration",
        verification_timeout: float = 300.0,
        session_ttl_seconds: float = 600.0,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store = store
        self.integration_path = Path(integration_path).resolve()
        self.candidates_root = Path(candidates_root).resolve()
        self.integration_branch = integration_branch
        self.verification_timeout = verification_timeout
        self.session_ttl_seconds = session_ttl_seconds

    def _git(
        self,
        cwd: Path,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
        return result

    def _changed_worktree_paths(self, worktree: Path) -> list[str]:
        tracked = self._git(worktree, "diff", "--name-only", "HEAD", "--").stdout.splitlines()
        untracked = self._git(
            worktree, "ls-files", "--others", "--exclude-standard"
        ).stdout.splitlines()
        return sorted({path.strip().replace("\\", "/") for path in [*tracked, *untracked] if path.strip()})

    def _assert_owned(self, task_id: str, session_id: str, paths: list[str]) -> None:
        if not paths:
            return
        leases = [
            lease
            for lease in ResourceLeaseManager(self.store).list_active()
            if lease.task_id == task_id
            and lease.agent_session_id == session_id
            and lease.access_mode is AccessMode.WRITE
            and lease.resource_type in {ResourceType.FILE, ResourceType.TREE}
        ]
        unowned: list[str] = []
        for path in paths:
            if not any(
                resources_overlap(
                    ResourceType.FILE,
                    path,
                    lease.resource_type,
                    lease.resource_key,
                )
                for lease in leases
            ):
                unowned.append(path)
        if unowned:
            self.store.append_event(
                WorkspaceEvent(
                    event="integration.unowned_change",
                    task_id=task_id,
                    session_id=session_id,
                    detail=", ".join(unowned)[:4000],
                )
            )
            raise UnownedChangeError(unowned)

    def _ensure_integration_worktree(self) -> None:
        if self.integration_path.exists():
            branch = self._git(
                self.integration_path, "branch", "--show-current"
            ).stdout.strip()
            if branch != self.integration_branch:
                raise RuntimeError(
                    f"integration worktree branch mismatch: {branch!r}"
                )
            if self._git(
                self.integration_path, "status", "--porcelain"
            ).stdout.strip():
                raise RuntimeError("integration worktree is dirty")
            return

        self.integration_path.parent.mkdir(parents=True, exist_ok=True)
        branch_exists = self._git(
            self.repo_root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{self.integration_branch}",
            check=False,
        ).returncode == 0
        args = ["worktree", "add"]
        if branch_exists:
            args.extend([str(self.integration_path), self.integration_branch])
        else:
            args.extend(["-b", self.integration_branch, str(self.integration_path), "HEAD"])
        self._git(self.repo_root, *args)

    def _commit_task_changes(self, task_id: str, worktree: Path) -> str:
        changed = self._changed_worktree_paths(worktree)
        if changed:
            self._git(worktree, "add", "--all")
            self._git(
                worktree,
                "commit",
                "-m",
                f"mawc({task_id}): verified task changes",
            )
        return self._git(worktree, "rev-parse", "HEAD").stdout.strip()

    def _task_branch(self, worktree: Path) -> str:
        branch = self._git(worktree, "branch", "--show-current").stdout.strip()
        if not branch:
            raise RuntimeError("task worktree is detached")
        return branch

    def _branch_changed_paths(self, task_branch: str) -> list[str]:
        merge_base = self._git(
            self.repo_root,
            "merge-base",
            self.integration_branch,
            task_branch,
        ).stdout.strip()
        result = self._git(
            self.repo_root,
            "diff",
            "--name-only",
            f"{merge_base}..{task_branch}",
            "--",
        ).stdout
        return sorted(
            {line.strip().replace("\\", "/") for line in result.splitlines() if line.strip()}
        )

    def _create_candidate(self, task_id: str) -> Path:
        candidate = (
            self.candidates_root / task_id / str(uuid4())
        ).resolve()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._git(
            self.repo_root,
            "worktree",
            "add",
            "--detach",
            str(candidate),
            self.integration_branch,
        )
        return candidate

    def _verify_candidate(self, task, candidate: Path) -> tuple[bool, str]:
        if not task.verification_argv:
            return False, "no verification commands configured"
        for argv in task.verification_argv:
            if not argv or not isinstance(argv[0], str) or not argv[0].strip():
                return False, "invalid verification argv"
            try:
                completed = subprocess.run(
                    argv,
                    cwd=candidate,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self.verification_timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return False, f"{type(exc).__name__}: {exc}"
            if completed.returncode != 0:
                detail = (
                    f"rc={completed.returncode}; stdout={completed.stdout[-1500:]!r}; "
                    f"stderr={completed.stderr[-1500:]!r}"
                )
                return False, detail[:4000]
        return True, f"{len(task.verification_argv)} integration verification command(s) passed"

    def _release_session(self, task, session) -> None:
        for lease in ResourceLeaseManager(self.store).list_active():
            if lease.task_id == task.id and lease.agent_session_id == session.session_id:
                ResourceLeaseManager(self.store).release(lease.lease_id)

        now = datetime.now(timezone.utc)
        freed = session.model_copy(
            update={
                "state": SessionState.ACTIVE,
                "task_id": None,
                "process_id": None,
                "worktree_path": None,
                "stdout_log_path": None,
                "stderr_log_path": None,
                "heartbeat_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=self.session_ttl_seconds)).isoformat(),
                "last_observation": f"merged task {task.id}",
            }
        )
        self.store.save_session(freed)

    def integrate(self, task_id: str) -> IntegrationOutcome:
        task = self.store.get_workspace_task(task_id)
        if task.state is not WorkTaskState.VERIFIED:
            raise RuntimeError("task must be VERIFIED before integration")
        if not task.assigned_session_id:
            raise RuntimeError("verified task has no assigned session")
        session = self.store.get_session(task.assigned_session_id)
        if session.state is not SessionState.VERIFYING:
            raise RuntimeError("assigned session must remain VERIFYING until merge")
        if not session.worktree_path:
            raise RuntimeError("verified session has no task worktree")
        worktree = Path(session.worktree_path).resolve()
        if not worktree.exists():
            raise FileNotFoundError(worktree)

        dirty_paths = self._changed_worktree_paths(worktree)
        self._assert_owned(task.id, session.session_id, dirty_paths)
        task_commit = self._commit_task_changes(task.id, worktree)
        task_branch = self._task_branch(worktree)

        self._ensure_integration_worktree()
        branch_paths = self._branch_changed_paths(task_branch)
        self._assert_owned(task.id, session.session_id, branch_paths)

        candidate = self._create_candidate(task.id)
        merge = self._git(
            candidate,
            "merge",
            "--no-ff",
            "--no-edit",
            task_branch,
            check=False,
        )
        if merge.returncode != 0:
            detail = (merge.stderr or merge.stdout).strip()[:4000]
            self.store.append_event(
                WorkspaceEvent(
                    event="integration.merge_failed",
                    task_id=task.id,
                    session_id=session.session_id,
                    detail=detail,
                )
            )
            raise RuntimeError(f"integration merge failed: {detail}")

        passed, detail = self._verify_candidate(task, candidate)
        if not passed:
            self.store.append_event(
                WorkspaceEvent(
                    event="integration.verification_failed",
                    task_id=task.id,
                    session_id=session.session_id,
                    detail=detail,
                )
            )
            raise IntegrationVerificationError(detail)

        integration_commit = self._git(candidate, "rev-parse", "HEAD").stdout.strip()
        if self._git(
            self.integration_path, "status", "--porcelain"
        ).stdout.strip():
            raise RuntimeError("integration worktree became dirty")
        self._git(
            self.integration_path,
            "merge",
            "--ff-only",
            integration_commit,
        )

        merged_task = task.model_copy(
            update={"state": WorkTaskState.MERGED, "updated_at": utc_now()}
        )
        self.store.save_workspace_task(merged_task)
        self._release_session(merged_task, session)
        self.store.append_event(
            WorkspaceEvent(
                event="integration.merged",
                task_id=task.id,
                session_id=session.session_id,
                detail=f"integration_commit={integration_commit}",
            )
        )
        return IntegrationOutcome(
            task_id=task.id,
            merged=True,
            task_commit=task_commit,
            integration_commit=integration_commit,
            candidate_path=candidate,
        )
