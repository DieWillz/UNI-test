from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class CheckpointType(str, Enum):
    FEATURE_VERIFIED = "feature_verified"
    PROJECT_KNOWN_GOOD = "project_known_good"


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        if key in {"owner_verified_at", "owner_note", "owner_approval_ref"}:
            raise ValueError(
                f"owner verification field {key} must be a non-empty string"
            )
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("checkpoint evidence fields must be arrays of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("checkpoint evidence fields must contain non-empty strings")
    return tuple(value)


@dataclass(frozen=True)
class Checkpoint:
    id: str
    type: CheckpointType
    label: str
    created_at: str
    owner_verified_at: str
    owner_note: str
    owner_approval_ref: str
    master_revision: str
    source_git_revision: str
    snapshot_ref: str
    verified_tasks: tuple[str, ...] = ()
    verified_features: tuple[str, ...] = ()
    test_evidence: tuple[str, ...] = ()
    architecture_evidence: tuple[str, ...] = ()
    verification_invariant_evidence: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "created_at": self.created_at,
            "owner_verified_at": self.owner_verified_at,
            "owner_note": self.owner_note,
            "owner_approval_ref": self.owner_approval_ref,
            "master_revision": self.master_revision,
            "source_git_revision": self.source_git_revision,
            "snapshot_ref": self.snapshot_ref,
            "verified_tasks": list(self.verified_tasks),
            "verified_features": list(self.verified_features),
            "test_evidence": list(self.test_evidence),
            "architecture_evidence": list(self.architecture_evidence),
            "verification_invariant_evidence": list(self.verification_invariant_evidence),
            "dependencies": list(self.dependencies),
            "files": list(self.files),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Checkpoint":
        return cls(
            id=_required_string(data, "id"),
            type=CheckpointType(_required_string(data, "type")),
            label=_required_string(data, "label"),
            created_at=_required_string(data, "created_at"),
            owner_verified_at=_required_string(data, "owner_verified_at"),
            owner_note=_required_string(data, "owner_note"),
            owner_approval_ref=_required_string(data, "owner_approval_ref"),
            master_revision=_required_string(data, "master_revision"),
            source_git_revision=_required_string(data, "source_git_revision"),
            snapshot_ref=_required_string(data, "snapshot_ref"),
            verified_tasks=_strings(data.get("verified_tasks")),
            verified_features=_strings(data.get("verified_features")),
            test_evidence=_strings(data.get("test_evidence")),
            architecture_evidence=_strings(data.get("architecture_evidence")),
            verification_invariant_evidence=_strings(
                data.get("verification_invariant_evidence")
            ),
            dependencies=_strings(data.get("dependencies")),
            files=_strings(data.get("files")),
        )


@dataclass(frozen=True)
class RestorePlan:
    source_checkpoint: Checkpoint
    target_revision: str
    changed_files: tuple[str, ...]
    files_that_would_be_removed: tuple[str, ...]
    conflicts: tuple[str, ...]
    current_dirty_state: tuple[str, ...]
    safe_target_workspace: str
    activation_allowed: bool = False


@dataclass(frozen=True)
class EmergencySnapshot:
    id: str
    label: str
    created_at: str
    head_revision: str
    location: str
    patch_file: str
    untracked_archive: str
    dirty_state: tuple[str, ...]
