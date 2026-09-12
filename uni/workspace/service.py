from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .models import OwnerVerificationRecord, TaskWorkspaceView, WorkspaceOverview
from .progress import calculate_progress
from .sources import (
    AgentSource,
    CheckpointSource,
    EmptyAgentSource,
    EmptyCheckpointSource,
    EmptyTaskSource,
    RevisionSource,
    StaticRevisionSource,
    TaskSource,
)


class WorkspaceError(RuntimeError):
    pass


class UnknownWorkspaceTask(WorkspaceError):
    pass


class WorkspaceValidationError(WorkspaceError):
    pass


class WorkspaceSourceError(WorkspaceError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceService:
    def __init__(
        self,
        *,
        agent_source: AgentSource | None = None,
        task_source: TaskSource | None = None,
        checkpoint_source: CheckpointSource | None = None,
        revision_source: RevisionSource | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.agent_source = agent_source or EmptyAgentSource()
        self.task_source = task_source or EmptyTaskSource()
        self.checkpoint_source = checkpoint_source or EmptyCheckpointSource()
        self.revision_source = revision_source or StaticRevisionSource()
        self.clock = clock or _utc_now

    def get_overview(self) -> WorkspaceOverview:
        tasks = tuple(self._with_progress(task) for task in self.task_source.list_tasks())
        return WorkspaceOverview(
            master_revision=self.revision_source.get_master_revision(),
            updated_at=self.clock(),
            agents=tuple(self.agent_source.list_agents()),
            tasks=tasks,
            checkpoints=tuple(self.checkpoint_source.list_checkpoints()),
        )

    def record_owner_verification(
        self,
        task_id: str,
        *,
        verified: bool,
        note: str,
        owner_identity: str,
    ) -> TaskWorkspaceView:
        task = self.task_source.get_task(task_id)
        if task is None:
            raise UnknownWorkspaceTask(task_id)

        clean_note = note.strip()
        clean_owner = owner_identity.strip()
        if not clean_note:
            raise WorkspaceValidationError("owner verification note is required")
        if not clean_owner:
            raise WorkspaceValidationError("owner identity is required")
        if verified:
            self._validate_approval(task)

        source_revision = task.source_revision or self.revision_source.get_master_revision()
        if verified and not source_revision:
            raise WorkspaceValidationError("source revision is required for owner approval")
        record = OwnerVerificationRecord(
            verified=verified,
            owner_identity=clean_owner,
            timestamp=self.clock(),
            note=clean_note,
            task_revision=task.task_revision,
            verification_evidence_ref=task.verification_evidence_ref,
            source_revision=source_revision,
        )
        target_status = task.status if verified else "development"
        updated = self.task_source.record_owner_verification(
            task_id,
            record,
            status=target_status,
        )
        self._validate_source_result(updated, record, target_status)
        return self._with_progress(updated)

    @staticmethod
    def _validate_approval(task: TaskWorkspaceView) -> None:
        if task.acceptance_total <= 0 or task.acceptance_passed < task.acceptance_total:
            raise WorkspaceValidationError("acceptance criteria are not complete")
        if not task.agent_verified:
            raise WorkspaceValidationError("agent verification is not complete")
        if not task.task_revision:
            raise WorkspaceValidationError("task revision is required for owner approval")
        if not task.verification_evidence_ref:
            raise WorkspaceValidationError("verification evidence reference is required")

    @staticmethod
    def _validate_source_result(
        task: TaskWorkspaceView,
        record: OwnerVerificationRecord,
        status: str,
    ) -> None:
        if task.owner_verification != record:
            raise WorkspaceSourceError("task source did not persist owner verification record")
        if task.owner_verified is not record.verified:
            raise WorkspaceSourceError("task source returned wrong owner verification state")
        if task.status != status:
            raise WorkspaceSourceError("task source returned wrong task status")

    @staticmethod
    def _with_progress(task: TaskWorkspaceView) -> TaskWorkspaceView:
        progress = calculate_progress(
            task.acceptance_total,
            task.acceptance_passed,
            task.agent_verified,
            task.owner_verified,
        )
        return replace(task, progress=progress)
