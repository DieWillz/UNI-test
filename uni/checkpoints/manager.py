from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .git_backend import GitBackend
from .models import Checkpoint, CheckpointType, EmergencySnapshot, RestorePlan


class CheckpointError(RuntimeError):
    pass


class CheckpointSafetyError(CheckpointError):
    pass


class UnknownCheckpointError(CheckpointError):
    pass


def _tuple(values: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


class CheckpointManager:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        store_root: Path | str | None = None,
        git_backend: GitBackend | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store_root = Path(store_root or (self.repo_root / ".uni-dev" / "checkpoints"))
        self.git = git_backend or GitBackend(self.repo_root)

    @property
    def metadata_dir(self) -> Path:
        return self.store_root / "metadata"

    @property
    def snapshots_dir(self) -> Path:
        return self.store_root / "snapshots"

    def _checkpoint_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"cp-{stamp}-{uuid4().hex[:12]}"

    def _metadata_path(self, checkpoint_id: str) -> Path:
        if not checkpoint_id or Path(checkpoint_id).name != checkpoint_id:
            raise UnknownCheckpointError(checkpoint_id)
        if "/" in checkpoint_id or "\\" in checkpoint_id:
            raise UnknownCheckpointError(checkpoint_id)
        return self.metadata_dir / f"{checkpoint_id}.json"

    def _persist(self, checkpoint: Checkpoint) -> Checkpoint:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        path = self._metadata_path(checkpoint.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return checkpoint

    @staticmethod
    def _require_owner(
        owner_verified_at: str | None,
        owner_note: str | None,
        owner_approval_ref: str | None,
    ) -> None:
        if not owner_verified_at or not owner_note or not owner_approval_ref:
            raise CheckpointSafetyError(
                "owner verification is required and must be stored separately"
            )

    @staticmethod
    def _require_master(master_revision: str | None) -> None:
        if not master_revision:
            raise CheckpointSafetyError("master revision is required")

    @staticmethod
    def _require_feature_evidence(test_evidence: tuple[str, ...]) -> None:
        if not test_evidence:
            raise CheckpointSafetyError("feature checkpoint requires evidence")

    @staticmethod
    def _validate_checkpoint(checkpoint: Checkpoint) -> None:
        CheckpointManager._require_owner(
            checkpoint.owner_verified_at,
            checkpoint.owner_note,
            checkpoint.owner_approval_ref,
        )
        CheckpointManager._require_master(checkpoint.master_revision)
        if not checkpoint.source_git_revision or not checkpoint.snapshot_ref:
            raise CheckpointSafetyError("checkpoint revision metadata is required")
        if checkpoint.type is CheckpointType.FEATURE_VERIFIED:
            CheckpointManager._require_feature_evidence(checkpoint.test_evidence)
            if not checkpoint.files or not checkpoint.snapshot_ref.startswith(
                "feature-tree:sha256:"
            ):
                raise CheckpointSafetyError("feature checkpoint metadata is invalid")
        elif checkpoint.type is CheckpointType.PROJECT_KNOWN_GOOD:
            CheckpointManager._require_project_evidence(
                checkpoint.test_evidence,
                checkpoint.architecture_evidence,
                checkpoint.verification_invariant_evidence,
            )
            if not checkpoint.snapshot_ref.startswith("git-tree:"):
                raise CheckpointSafetyError("project checkpoint metadata is invalid")

    @staticmethod
    def _require_project_evidence(
        test_evidence: tuple[str, ...],
        architecture_evidence: tuple[str, ...],
        invariant_evidence: tuple[str, ...],
    ) -> None:
        missing: list[str] = []
        if not test_evidence:
            missing.append("test evidence")
        if not architecture_evidence:
            missing.append("architecture evidence")
        if not invariant_evidence:
            missing.append("verification invariant evidence")
        if missing:
            raise CheckpointSafetyError(
                "project known good requires " + ", ".join(missing)
            )

    def _normalize_feature_files(self, files: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in files:
            source = self.git.resolve_repo_path(str(item))
            if not source.is_file() or source.is_symlink():
                raise CheckpointSafetyError(f"feature file is not snapshot-safe: {item}")
            relative = source.relative_to(self.repo_root).as_posix()
            normalized.append(relative)
        result = tuple(sorted(set(normalized)))
        if not result:
            raise CheckpointSafetyError("feature checkpoint requires files")
        return result

    def _snapshot_feature_files(
        self, checkpoint_id: str, files: tuple[str, ...]
    ) -> str:
        root = self.snapshots_dir / checkpoint_id
        files_root = root / "files"
        if root.exists():
            raise CheckpointSafetyError(f"snapshot already exists: {checkpoint_id}")
        files_root.mkdir(parents=True, exist_ok=False)

        manifest: dict[str, str] = {}
        digest = hashlib.sha256()
        for relative in files:
            source = self.git.resolve_repo_path(relative)
            data = source.read_bytes()
            file_hash = hashlib.sha256(data).hexdigest()
            manifest[relative] = file_hash
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\n")
            target = files_root / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return f"feature-tree:sha256:{digest.hexdigest()}"

    def create_feature_checkpoint(
        self,
        label: str,
        *,
        files: Iterable[str],
        master_revision: str,
        owner_verified_at: str | None,
        owner_note: str | None,
        owner_approval_ref: str | None,
        dependencies: Iterable[str] | None = None,
        verified_tasks: Iterable[str] | None = None,
        verified_features: Iterable[str] | None = None,
        test_evidence: Iterable[str] | None = None,
        architecture_evidence: Iterable[str] | None = None,
        verification_invariant_evidence: Iterable[str] | None = None,
    ) -> Checkpoint:
        self._require_owner(owner_verified_at, owner_note, owner_approval_ref)
        self._require_master(master_revision)
        normalized_files = self._normalize_feature_files(files)
        tests = _tuple(test_evidence)
        self._require_feature_evidence(tests)

        checkpoint_id = self._checkpoint_id()
        snapshot_ref = self._snapshot_feature_files(checkpoint_id, normalized_files)
        checkpoint = Checkpoint(
            id=checkpoint_id,
            type=CheckpointType.FEATURE_VERIFIED,
            label=str(label),
            created_at=datetime.now(timezone.utc).isoformat(),
            owner_verified_at=str(owner_verified_at),
            owner_note=str(owner_note),
            owner_approval_ref=str(owner_approval_ref),
            master_revision=str(master_revision),
            source_git_revision=self.git.head_revision(),
            snapshot_ref=snapshot_ref,
            verified_tasks=_tuple(verified_tasks),
            verified_features=_tuple(verified_features),
            test_evidence=tests,
            architecture_evidence=_tuple(architecture_evidence),
            verification_invariant_evidence=_tuple(
                verification_invariant_evidence
            ),
            dependencies=_tuple(dependencies),
            files=normalized_files,
        )
        return self._persist(checkpoint)

    def create_project_checkpoint(
        self,
        label: str,
        *,
        master_revision: str,
        owner_verified_at: str | None,
        owner_note: str | None,
        owner_approval_ref: str | None,
        verified_tasks: Iterable[str] | None = None,
        verified_features: Iterable[str] | None = None,
        test_evidence: Iterable[str] | None = None,
        architecture_evidence: Iterable[str] | None = None,
        verification_invariant_evidence: Iterable[str] | None = None,
    ) -> Checkpoint:
        self._require_owner(owner_verified_at, owner_note, owner_approval_ref)
        self._require_master(master_revision)
        tests = _tuple(test_evidence)
        architecture = _tuple(architecture_evidence)
        invariant = _tuple(verification_invariant_evidence)
        self._require_project_evidence(tests, architecture, invariant)
        if not self.git.is_clean():
            raise CheckpointSafetyError(
                "dirty workspace cannot become PROJECT_KNOWN_GOOD"
            )

        source_revision = self.git.head_revision()
        tree_revision = self.git.tree_revision(source_revision)
        if self.git.head_revision() != source_revision or not self.git.is_clean():
            raise CheckpointSafetyError(
                "workspace changed during capture; PROJECT_KNOWN_GOOD blocked"
            )
        checkpoint = Checkpoint(
            id=self._checkpoint_id(),
            type=CheckpointType.PROJECT_KNOWN_GOOD,
            label=str(label),
            created_at=datetime.now(timezone.utc).isoformat(),
            owner_verified_at=str(owner_verified_at),
            owner_note=str(owner_note),
            owner_approval_ref=str(owner_approval_ref),
            master_revision=str(master_revision),
            source_git_revision=source_revision,
            snapshot_ref=f"git-tree:{tree_revision}",
            verified_tasks=_tuple(verified_tasks),
            verified_features=_tuple(verified_features),
            test_evidence=tests,
            architecture_evidence=architecture,
            verification_invariant_evidence=invariant,
        )
        return self._persist(checkpoint)

    def inspect_checkpoint(self, checkpoint_id: str) -> Checkpoint:
        path = self._metadata_path(checkpoint_id)
        if not path.is_file():
            raise UnknownCheckpointError(checkpoint_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            checkpoint = Checkpoint.from_dict(raw)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise CheckpointSafetyError(
                f"checkpoint metadata is invalid: {checkpoint_id}: {exc}"
            ) from exc
        if checkpoint.id != checkpoint_id:
            raise CheckpointSafetyError("checkpoint id mismatch")
        self._validate_checkpoint(checkpoint)
        return checkpoint

    def list_checkpoints(self) -> tuple[Checkpoint, ...]:
        if not self.metadata_dir.exists():
            return ()
        checkpoints = [
            self.inspect_checkpoint(path.stem)
            for path in sorted(self.metadata_dir.glob("*.json"))
        ]
        return tuple(sorted(checkpoints, key=lambda item: item.created_at))

    @staticmethod
    def _snapshot_member_path(root: Path, relative: str) -> Path:
        files_root = (root / "files").resolve()
        candidate = (files_root / relative).resolve()
        try:
            candidate.relative_to(files_root)
        except ValueError as exc:
            raise CheckpointSafetyError(
                f"unsafe snapshot path: {relative}"
            ) from exc
        return candidate

    def _feature_manifest(self, checkpoint: Checkpoint) -> dict[str, str]:
        root = self.snapshots_dir / checkpoint.id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise CheckpointSafetyError("feature snapshot manifest is missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CheckpointSafetyError("feature snapshot manifest is invalid") from exc
        if not isinstance(manifest, dict):
            raise CheckpointSafetyError("feature snapshot manifest is invalid")

        digest = hashlib.sha256()
        normalized: dict[str, str] = {}
        for relative in sorted(manifest):
            expected = str(manifest[relative])
            snapshot_file = self._snapshot_member_path(root, str(relative))
            if not snapshot_file.is_file():
                raise CheckpointSafetyError(f"feature snapshot file missing: {relative}")
            actual = hashlib.sha256(snapshot_file.read_bytes()).hexdigest()
            if actual != expected:
                raise CheckpointSafetyError(f"feature snapshot hash mismatch: {relative}")
            normalized[str(relative)] = expected
            digest.update(str(relative).encode("utf-8"))
            digest.update(b"\0")
            digest.update(expected.encode("ascii"))
            digest.update(b"\n")

        expected_ref = f"feature-tree:sha256:{digest.hexdigest()}"
        if checkpoint.snapshot_ref != expected_ref:
            raise CheckpointSafetyError("feature snapshot reference mismatch")
        return normalized

    def _verify_project_snapshot(self, checkpoint: Checkpoint) -> None:
        actual_tree = self.git.tree_revision(checkpoint.source_git_revision)
        if checkpoint.snapshot_ref != f"git-tree:{actual_tree}":
            raise CheckpointSafetyError("project snapshot reference mismatch")

    def prepare_restore(self, checkpoint_id: str) -> RestorePlan:
        checkpoint = self.inspect_checkpoint(checkpoint_id)
        dirty_entries = self.git.status_entries()
        dirty_state = tuple(
            f"{entry.code} {entry.path}" for entry in dirty_entries
        )
        safe_target = self.store_root / "restore-workspaces" / checkpoint.id

        if checkpoint.type is CheckpointType.PROJECT_KNOWN_GOOD:
            self._verify_project_snapshot(checkpoint)
            commit_changes = self.git.diff_name_status(
                checkpoint.source_git_revision, "HEAD"
            )
            changed = {path for _, path in commit_changes}
            changed.update(entry.path for entry in dirty_entries)
            removals = {
                path for status, path in commit_changes if status.startswith("A")
            }
            conflicts = {entry.path for entry in dirty_entries}
        else:
            manifest = self._feature_manifest(checkpoint)
            changed = set()
            for relative, expected_hash in manifest.items():
                current = self.git.resolve_repo_path(relative)
                if not current.is_file():
                    changed.add(relative)
                    continue
                actual_hash = hashlib.sha256(current.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    changed.add(relative)
            removals = set()
            feature_files = set(manifest)
            conflicts = {
                entry.path for entry in dirty_entries if entry.path in feature_files
            }

        return RestorePlan(
            source_checkpoint=checkpoint,
            target_revision=checkpoint.source_git_revision,
            changed_files=tuple(sorted(changed)),
            files_that_would_be_removed=tuple(sorted(removals)),
            conflicts=tuple(sorted(conflicts)),
            current_dirty_state=dirty_state,
            safe_target_workspace=str(safe_target),
            activation_allowed=False,
        )

    def create_emergency_snapshot(self, label: str) -> EmergencySnapshot:
        return self.git.create_emergency_snapshot(
            self.store_root / "emergency", label
        )
