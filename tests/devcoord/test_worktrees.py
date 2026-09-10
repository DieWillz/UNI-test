from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from uni.devcoord.worktrees import WorktreeCollisionError, WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "mawc@example.invalid")
    _git(repo, "config", "user.name", "MAWC Test")
    (repo / "shared.txt").write_text("committed", encoding="utf-8")
    _git(repo, "add", "shared.txt")
    _git(repo, "commit", "-qm", "base")
    return repo

def test_task_worktree_uses_committed_base_not_dirty_shared_tree(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "shared.txt").write_text("dirty-shared-change", encoding="utf-8")
    manager = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")

    ref = manager.create("hermes", "UNI-200")

    assert ref.agent_id == "hermes"
    assert ref.task_id == "UNI-200"
    assert ref.branch == "mawc/hermes/UNI-200"
    assert ref.path == (tmp_path / "worktrees" / "hermes" / "UNI-200").resolve()
    assert (ref.path / "shared.txt").read_text(encoding="utf-8") == "committed"
    assert (repo / "shared.txt").read_text(encoding="utf-8") == "dirty-shared-change"
    assert _git(ref.path, "branch", "--show-current") == ref.branch


def test_worktree_collision_is_refused(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    manager = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    manager.create("codex", "UNI-201")

    with pytest.raises(WorktreeCollisionError):
        manager.create("codex", "UNI-201")

def test_snapshot_is_read_only_and_captures_task_state(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    manager = WorktreeManager(repo, worktrees_root=tmp_path / "worktrees")
    ref = manager.create("hermes", "UNI-202")
    (ref.path / "shared.txt").write_text("task-change", encoding="utf-8")
    (ref.path / "new.txt").write_text("untracked", encoding="utf-8")
    canonical_before = _git(repo, "status", "--porcelain")

    snapshot = manager.snapshot(ref)

    assert snapshot.branch == ref.branch
    assert snapshot.head_commit == _git(ref.path, "rev-parse", "HEAD")
    assert "shared.txt" in snapshot.status_porcelain
    assert "new.txt" in snapshot.status_porcelain
    assert "-committed" in snapshot.diff_text
    assert "+task-change" in snapshot.diff_text
    assert _git(repo, "status", "--porcelain") == canonical_before
