from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class WorktreeCollisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorktreeRef:
    agent_id: str
    task_id: str
    branch: str
    path: Path


class WorktreeManager:
    """Create isolated task worktrees without touching shared dirty changes."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        worktrees_root: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_root = Path(
            worktrees_root or (self.repo_root / ".uni-dev" / "worktrees")
        ).resolve()

    @staticmethod
    def _validate_segment(value: str, label: str) -> str:
        if not _SEGMENT.fullmatch(value):
            raise ValueError(f"unsafe {label}: {value!r}")
        return value

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            check=check,
            capture_output=True,
            text=True,
        )

    def _branch_exists(self, branch: str) -> bool:
        result = self._git(
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        )
        return result.returncode == 0

    def create(
        self,
        agent_id: str,
        task_id: str,
        *,
        base_ref: str = "HEAD",
    ) -> WorktreeRef:
        agent = self._validate_segment(agent_id, "agent id")
        task = self._validate_segment(task_id, "task id")
        branch = f"mawc/{agent}/{task}"
        target = (self.worktrees_root / agent / task).resolve()
        if self.worktrees_root not in target.parents:
            raise ValueError("worktree path escapes configured root")
        if target.exists() or self._branch_exists(branch):
            raise WorktreeCollisionError(f"worktree already exists for {agent}/{task}")

        target.parent.mkdir(parents=True, exist_ok=True)
        result = self._git(
            "worktree",
            "add",
            "-b",
            branch,
            str(target),
            base_ref,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"git worktree add failed: {detail}")
        return WorktreeRef(
            agent_id=agent,
            task_id=task,
            branch=branch,
            path=target,
        )

    def snapshot(self, ref: WorktreeRef) -> "WorktreeSnapshot":
        if not ref.path.exists():
            raise FileNotFoundError(ref.path)

        def run(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=ref.path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        current_branch = run("branch", "--show-current")
        if current_branch != ref.branch:
            raise RuntimeError(
                f"worktree branch mismatch: expected {ref.branch}, got {current_branch}"
            )
        return WorktreeSnapshot(
            agent_id=ref.agent_id,
            task_id=ref.task_id,
            branch=ref.branch,
            path=ref.path,
            head_commit=run("rev-parse", "HEAD"),
            status_porcelain=run("status", "--porcelain"),
            diff_text=run("diff", "--binary"),
        )


@dataclass(frozen=True)
class WorktreeSnapshot:
    agent_id: str
    task_id: str
    branch: str
    path: Path
    head_commit: str
    status_porcelain: str
    diff_text: str
