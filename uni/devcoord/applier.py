"""Applier: apply a proposed code patch on a review branch and test it.

Hard safety contract (not negotiable):
- ``apply_and_test`` NEVER commits and NEVER merges. It applies the patch on a
  throwaway ``review/<task_id>`` branch, runs the test suite, and either leaves
  the branch for human review (status ``awaiting_human_confirmation``) or
  reverts it (status ``reverted``).
- The only path to merge is ``confirm_merge``, which is intended to be called
  explicitly by a human (via the console / CLI), never automatically.

This guard exists because we have already seen different AIs make contradictory
factual claims about the same code; an automatic merge of an unverified patch
would silently entrench a wrong claim. A human must inspect the diff + test
output first.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

_CHECK_ARCH_SCRIPT = "scripts/check_architecture.py"


class ApplyResult(BaseModel):
    branch: str
    diff: str = ""
    tests_passed: bool = False
    test_output: str = ""
    status: str  # "awaiting_human_confirmation" | "reverted"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Applier:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._last_base: str | None = None

    # -- helpers (sync; run off the event loop via asyncio.to_thread) --------
    @staticmethod
    def _run(args: list[str], cwd: str, timeout: float = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _current_branch(self, cwd: str) -> str:
        return self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()

    def _branch_exists(self, cwd: str, branch: str) -> bool:
        return self._run(["git", "rev-parse", "--verify", branch], cwd).returncode == 0

    # -- public async API -----------------------------------------------------
    async def apply_and_test(self, task_id: str, patch: str) -> ApplyResult:
        """Apply ``patch`` on ``review/<task_id>`` and run the test gate.

        NEVER commits or merges. Returns status ``awaiting_human_confirmation``
        on green tests, ``reverted`` on red tests or an unapplicable patch.
        """
        return await asyncio.to_thread(self._apply_sync, task_id, patch)

    async def confirm_merge(self, task_id: str) -> bool:
        """Merge ``review/<task_id>`` into the current branch.

        Intended to be called ONLY by a human after inspecting the diff and test
        output. Not invoked anywhere automatically.
        """
        return await asyncio.to_thread(self._merge_sync, task_id)

    # -- implementation -------------------------------------------------------
    def _apply_sync(self, task_id: str, patch: str) -> ApplyResult:
        branch = f"review/{task_id}"
        cwd = str(self.repo_root)

        base = self._current_branch(cwd)
        # Create (or reset) the review branch from current HEAD.
        rc = self._run(["git", "checkout", "-B", branch], cwd)
        if rc.returncode != 0:
            return ApplyResult(
                branch=branch,
                tests_passed=False,
                test_output=f"git checkout -B failed:\n{rc.stderr}",
                status="reverted",
            )
        # Persist the base branch so a separate CLI process (confirm) can find it.
        self._write_base_marker(branch, base)
        self._last_base = base

        # Apply the patch.
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn"],
            cwd=cwd,
            input=patch,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            self._cleanup_branch(cwd, base, branch)
            return ApplyResult(
                branch=branch,
                tests_passed=False,
                test_output=f"patch did not apply:\n{proc.stdout}\n{proc.stderr}",
                status="reverted",
            )

        diff = self._run(["git", "diff", "--stat"], cwd).stdout

        # Test gate: pytest, plus the architecture audit if it ships with the repo.
        outputs: list[str] = []
        pytest = self._run(
            [sys.executable, "-m", "pytest", "-q"], cwd, timeout=600
        )
        outputs.append("=== pytest ===\n" + pytest.stdout + pytest.stderr)

        arch_script = self.repo_root / _CHECK_ARCH_SCRIPT
        if arch_script.exists():
            arch = self._run(
                [sys.executable, str(arch_script), "--strict"], cwd, timeout=300
            )
            outputs.append("=== check_architecture ===\n" + arch.stdout + arch.stderr)
            passed = pytest.returncode == 0 and arch.returncode == 0
        else:
            # Repo has no architecture gate; pytest alone decides.
            outputs.append("=== check_architecture ===\nskipped (script absent)")
            passed = pytest.returncode == 0

        if not passed:
            self._cleanup_branch(cwd, base, branch)
            return ApplyResult(
                branch=branch,
                diff=diff,
                tests_passed=False,
                test_output="\n".join(outputs),
                status="reverted",
            )

        # GREEN: leave the branch for human review. NEVER commit, NEVER merge.
        return ApplyResult(
            branch=branch,
            diff=diff,
            tests_passed=True,
            test_output="\n".join(outputs),
            status="awaiting_human_confirmation",
        )

    def _base_marker(self, branch: str) -> Path:
        return self.repo_root / ".uni-dev" / f"review_base_{branch.replace('/', '_')}.txt"

    def _write_base_marker(self, branch: str, base: str) -> None:
        marker = self._base_marker(branch)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(base, encoding="utf-8")

    def _read_base_marker(self, branch: str) -> str | None:
        marker = self._base_marker(branch)
        if marker.exists():
            return marker.read_text(encoding="utf-8").strip() or None
        return None

    def _cleanup_branch(self, cwd: str, base: str, branch: str) -> None:
        self._run(["git", "checkout", base], cwd)
        if self._branch_exists(cwd, branch):
            self._run(["git", "branch", "-D", branch], cwd)

    def _merge_sync(self, task_id: str) -> bool:
        branch = f"review/{task_id}"
        cwd = str(self.repo_root)
        if not self._branch_exists(cwd, branch):
            return False
        # This is the explicit human-confirmed step. apply_and_test never reaches
        # here. Commit the verified change on the review branch, then merge it
        # into the base branch.
        self._run(["git", "checkout", branch], cwd)
        self._run(["git", "add", "-A"], cwd)
        self._run(["git", "commit", "-q", "-m", f"devcoord: apply {branch}"], cwd)
        base = self._last_base or self._read_base_marker(branch) or self._current_branch(cwd)
        if base == branch:
            # Cannot determine a distinct base branch; refuse to merge into self.
            return False
        self._run(["git", "checkout", base], cwd)
        rc = self._run(
            ["git", "merge", branch, "--no-ff", "-m", f"devcoord: merge {branch}"],
            cwd,
            timeout=300,
        )
        return rc.returncode == 0
