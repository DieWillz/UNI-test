from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OwnerVerificationRecord:
    verified: bool
    owner_identity: str
    timestamp: str
    note: str
    task_revision: str
    verification_evidence_ref: str
    source_revision: str


@dataclass(frozen=True, slots=True)
class AgentWorkspaceView:
    id: str
    name: str
    task: str | None = None
    status: str = "idle"
    progress: int = 0
    updated_at: str = ""
    direction_revision: str = ""
    ack_revision: str = ""
    stale: bool = False
    owned_paths: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskWorkspaceView:
    id: str
    title: str
    description: str = ""
    agent: str | None = None
    status: str = "development"
    progress: int = 0
    updated_at: str = ""
    acceptance_total: int = 0
    acceptance_passed: int = 0
    agent_verified: bool = False
    owner_verified: bool = False
    owner_verified_at: str | None = None
    owner_note: str = ""
    dependencies: tuple[str, ...] = ()
    owner_verified_by: str | None = None
    task_revision: str = ""
    verification_evidence_ref: str = ""
    source_revision: str = ""
    owner_verification: OwnerVerificationRecord | None = None


@dataclass(frozen=True, slots=True)
class CheckpointView:
    id: str
    label: str
    created_at: str = ""
    reference: str = ""
    owner_verified: bool = False
    current: bool = False
    features: tuple[str, ...] = ()
    test_evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceOverview:
    master_revision: str
    updated_at: str
    agents: tuple[AgentWorkspaceView, ...] = ()
    tasks: tuple[TaskWorkspaceView, ...] = ()
    checkpoints: tuple[CheckpointView, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "master_revision": self.master_revision,
            "updated_at": self.updated_at,
            "agents": [_jsonable(asdict(item)) for item in self.agents],
            "tasks": [_jsonable(asdict(item)) for item in self.tasks],
            "checkpoints": [_jsonable(asdict(item)) for item in self.checkpoints],
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
