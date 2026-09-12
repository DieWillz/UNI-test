from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from uni.checkpoints import (
    CheckpointManager,
    CheckpointSafetyError,
    CheckpointType,
    GitBackend,
    UnknownCheckpointError,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Checkpoint Tests")
    (root / "app.txt").write_text("v1\n", encoding="utf-8")
    _commit_all(root, "initial")
    return root


@pytest.fixture
def manager(repo: Path, tmp_path: Path) -> CheckpointManager:
    return CheckpointManager(repo, store_root=tmp_path / "checkpoint-store")


def _owner() -> dict[str, str]:
    return {
        "owner_verified_at": "2026-09-11T20:00:00+00:00",
        "owner_note": "Owner manually verified the requested behavior.",
        "owner_approval_ref": "owner-chat:known-good-001",
    }


def _project_kwargs() -> dict[str, object]:
    return {
        **_owner(),
        "master_revision": "master-rev-abc",
        "verified_tasks": ["task-1"],
        "verified_features": ["feature-1"],
        "test_evidence": ["pytest: checkpoints green"],
        "architecture_evidence": ["architecture review: checkpoint boundaries"],
        "verification_invariant_evidence": ["invariant checker: PASS"],
    }


def test_project_checkpoint_requires_owner_verification(
    manager: CheckpointManager,
) -> None:
    kwargs = _project_kwargs()
    kwargs["owner_verified_at"] = None
    with pytest.raises(CheckpointSafetyError, match="owner verification"):
        manager.create_project_checkpoint("known-good", **kwargs)


def test_project_checkpoint_rejects_dirty_workspace(
    repo: Path, manager: CheckpointManager,
) -> None:
    (repo / "app.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(CheckpointSafetyError, match="dirty"):
        manager.create_project_checkpoint("known-good", **_project_kwargs())


def test_checkpoint_metadata_preserves_master_revision(
    manager: CheckpointManager,
) -> None:
    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    inspected = manager.inspect_checkpoint(checkpoint.id)
    assert inspected.master_revision == "master-rev-abc"
    assert inspected.owner_approval_ref == "owner-chat:known-good-001"


def test_prepare_restore_does_not_mutate_workspace(
    repo: Path, manager: CheckpointManager,
) -> None:
    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    (repo / "app.txt").write_text("dirty-after-checkpoint\n", encoding="utf-8")
    (repo / "sentinel.txt").write_text("keep me\n", encoding="utf-8")
    before_status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    before_app = (repo / "app.txt").read_bytes()
    before_sentinel = (repo / "sentinel.txt").read_bytes()

    plan = manager.prepare_restore(checkpoint.id)

    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == before_status
    assert (repo / "app.txt").read_bytes() == before_app
    assert (repo / "sentinel.txt").read_bytes() == before_sentinel
    assert plan.current_dirty_state
    assert plan.safe_target_workspace


def test_prepare_restore_lists_changes_and_removals(
    repo: Path, manager: CheckpointManager,
) -> None:
    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    (repo / "app.txt").write_text("v2\n", encoding="utf-8")
    (repo / "later.txt").write_text("newer work\n", encoding="utf-8")
    _commit_all(repo, "later")

    plan = manager.prepare_restore(checkpoint.id)
    assert "app.txt" in plan.changed_files
    assert "later.txt" in plan.changed_files
    assert "later.txt" in plan.files_that_would_be_removed


def test_unknown_checkpoint_is_blocked(manager: CheckpointManager) -> None:
    with pytest.raises(UnknownCheckpointError):
        manager.prepare_restore("does-not-exist")


def test_feature_and_project_checkpoints_are_distinct(
    repo: Path, manager: CheckpointManager,
) -> None:
    feature = manager.create_feature_checkpoint(
        "feature verified",
        files=["app.txt"],
        dependencies=["dep:core"],
        master_revision="master-rev-abc",
        verified_features=["feature-1"],
        test_evidence=["manual+pytest evidence"],
        **_owner(),
    )
    project = manager.create_project_checkpoint(
        "project known good", **_project_kwargs()
    )

    assert feature.type is CheckpointType.FEATURE_VERIFIED
    assert project.type is CheckpointType.PROJECT_KNOWN_GOOD
    assert feature.snapshot_ref.startswith("feature-tree:sha256:")
    assert project.snapshot_ref.startswith("git-tree:")
    assert feature.dependencies == ("dep:core",)


def test_feature_checkpoint_can_snapshot_selected_dirty_file_but_project_cannot(
    repo: Path, manager: CheckpointManager,
) -> None:
    (repo / "app.txt").write_text("owner-verified-dirty-feature\n", encoding="utf-8")
    feature = manager.create_feature_checkpoint(
        "feature verified", files=["app.txt"], master_revision="master-rev-abc",
        verified_features=["feature-1"], test_evidence=["owner exercised feature"],
        **_owner(),
    )
    assert feature.type is CheckpointType.FEATURE_VERIFIED
    with pytest.raises(CheckpointSafetyError, match="dirty"):
        manager.create_project_checkpoint("project known good", **_project_kwargs())


def test_git_backend_never_invokes_destructive_commands(repo: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    backend = GitBackend(repo, runner=runner)
    backend.head_revision()
    backend.tree_revision("HEAD")
    backend.status_entries()
    backend.diff_name_status("HEAD", "HEAD")

    forbidden = {"reset", "clean", "checkout", "restore"}
    assert calls
    assert all(not forbidden.intersection(call) for call in calls)


def test_emergency_snapshot_preserves_dirty_state_without_mutation(
    repo: Path, manager: CheckpointManager,
) -> None:
    (repo / "app.txt").write_text("dirty tracked\n", encoding="utf-8")
    (repo / "new.txt").write_text("untracked work\n", encoding="utf-8")
    before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")

    snapshot = manager.create_emergency_snapshot("before activation")

    assert Path(snapshot.location).is_dir()
    assert Path(snapshot.patch_file).is_file()
    assert Path(snapshot.untracked_archive).is_file()
    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == before


def test_tampered_checkpoint_losing_owner_approval_is_blocked(
    manager: CheckpointManager,
) -> None:
    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    metadata_path = manager.metadata_dir / f"{checkpoint.id}.json"
    import json

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["owner_approval_ref"] = ""
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CheckpointSafetyError, match="owner verification"):
        manager.inspect_checkpoint(checkpoint.id)


def test_tampered_feature_manifest_cannot_escape_snapshot_root(
    manager: CheckpointManager,
) -> None:
    import hashlib
    import json

    checkpoint = manager.create_feature_checkpoint(
        "feature verified",
        files=["app.txt"],
        master_revision="master-rev-abc",
        test_evidence=["owner exercised feature"],
        **_owner(),
    )
    escape = manager.snapshots_dir / "escape.txt"
    escape.write_text("outside snapshot\n", encoding="utf-8")
    digest = hashlib.sha256(escape.read_bytes()).hexdigest()
    manifest_path = manager.snapshots_dir / checkpoint.id / "manifest.json"
    manifest_path.write_text(
        json.dumps({"../../escape.txt": digest}), encoding="utf-8"
    )

    with pytest.raises(CheckpointSafetyError, match="snapshot path"):
        manager.prepare_restore(checkpoint.id)


def test_tampered_null_owner_reference_is_blocked(
    manager: CheckpointManager,
) -> None:
    import json

    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    metadata_path = manager.metadata_dir / f"{checkpoint.id}.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["owner_approval_ref"] = None
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CheckpointSafetyError, match="metadata is invalid"):
        manager.inspect_checkpoint(checkpoint.id)


def test_tampered_scalar_evidence_is_blocked(
    manager: CheckpointManager,
) -> None:
    import json

    checkpoint = manager.create_project_checkpoint(
        "known-good", **_project_kwargs()
    )
    metadata_path = manager.metadata_dir / f"{checkpoint.id}.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["test_evidence"] = "not-an-evidence-list"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CheckpointSafetyError, match="metadata is invalid"):
        manager.inspect_checkpoint(checkpoint.id)


def test_project_checkpoint_fails_closed_if_workspace_changes_during_capture(
    repo: Path, tmp_path: Path,
) -> None:
    class RacingGitBackend(GitBackend):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.clean_checks = 0

        def is_clean(self) -> bool:
            self.clean_checks += 1
            return self.clean_checks == 1

    manager = CheckpointManager(
        repo,
        store_root=tmp_path / "checkpoint-store",
        git_backend=RacingGitBackend(repo),
    )

    with pytest.raises(CheckpointSafetyError, match="changed during capture"):
        manager.create_project_checkpoint("known-good", **_project_kwargs())
