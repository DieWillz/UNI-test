from __future__ import annotations

from typing import Protocol, Sequence

from .models import (
    AgentWorkspaceView,
    CheckpointView,
    OwnerVerificationRecord,
    TaskWorkspaceView,
)


class AgentSource(Protocol):
    def list_agents(self) -> Sequence[AgentWorkspaceView]: ...


class TaskSource(Protocol):
    def list_tasks(self) -> Sequence[TaskWorkspaceView]: ...

    def get_task(self, task_id: str) -> TaskWorkspaceView | None: ...

    def record_owner_verification(
        self,
        task_id: str,
        record: OwnerVerificationRecord,
        *,
        status: str,
    ) -> TaskWorkspaceView: ...


class CheckpointSource(Protocol):
    def list_checkpoints(self) -> Sequence[CheckpointView]: ...


class RevisionSource(Protocol):
    def get_master_revision(self) -> str: ...


class TaskMutationUnavailable(RuntimeError):
    pass


class EmptyAgentSource:
    def list_agents(self) -> Sequence[AgentWorkspaceView]:
        return ()


class EmptyTaskSource:
    def list_tasks(self) -> Sequence[TaskWorkspaceView]:
        return ()

    def get_task(self, task_id: str) -> TaskWorkspaceView | None:
        return None

    def record_owner_verification(
        self,
        task_id: str,
        record: OwnerVerificationRecord,
        *,
        status: str,
    ) -> TaskWorkspaceView:
        raise TaskMutationUnavailable(f"no writable task source for {task_id}")


class EmptyCheckpointSource:
    def list_checkpoints(self) -> Sequence[CheckpointView]:
        return ()


class StaticRevisionSource:
    def __init__(self, revision: str = "") -> None:
        self.revision = revision

    def get_master_revision(self) -> str:
        return self.revision
