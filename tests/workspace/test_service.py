from dataclasses import replace

import pytest

from uni.workspace.models import AgentWorkspaceView, TaskWorkspaceView
from uni.workspace.service import WorkspaceService, WorkspaceValidationError
from uni.workspace.sources import EmptyAgentSource, EmptyCheckpointSource, StaticRevisionSource


NOW = "2026-09-11T20:00:00+00:00"


class RecordingTaskSource:
    def __init__(self, tasks=()):
        self.tasks = {task.id: task for task in tasks}
        self.records = []

    def list_tasks(self):
        return list(self.tasks.values())

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def record_owner_verification(self, task_id, record, *, status):
        task = self.tasks[task_id]
        updated = replace(
            task,
            status=status,
            owner_verified=record.verified,
            owner_verified_at=record.timestamp,
            owner_note=record.note,
            owner_verified_by=record.owner_identity,
            owner_verification=record,
        )
        self.tasks[task_id] = updated
        self.records.append(record)
        return updated


class StaticAgentSource:
    def __init__(self, agents=()):
        self.agents = list(agents)

    def list_agents(self):
        return list(self.agents)


def verified_task(**overrides):
    values = dict(
        id="task-1",
        title="Workspace backend",
        status="verifying",
        acceptance_total=7,
        acceptance_passed=7,
        agent_verified=True,
        task_revision="task-r3",
        verification_evidence_ref="pytest:workspace-green",
        source_revision="source-r9",
    )
    values.update(overrides)
    return TaskWorkspaceView(**values)


def make_service(task_source, *, agent_source=None):
    return WorkspaceService(
        task_source=task_source,
        agent_source=agent_source or EmptyAgentSource(),
        checkpoint_source=EmptyCheckpointSource(),
        revision_source=StaticRevisionSource("master-r1"),
        clock=lambda: NOW,
    )


def test_reject_returns_task_to_development_and_keeps_reason():
    source = RecordingTaskSource([verified_task()])
    result = make_service(source).record_owner_verification(
        "task-1", verified=False, note="Button still fails", owner_identity="owner",
    )
    assert result.status == "development"
    assert result.owner_verified is False
    assert result.owner_note == "Button still fails"
    assert source.records[-1].note == "Button still fails"


def test_owner_verification_records_identity_timestamp_and_revisions():
    source = RecordingTaskSource([verified_task()])
    result = make_service(source).record_owner_verification(
        "task-1", verified=True, note="Checked live", owner_identity="repo-owner",
    )
    record = result.owner_verification
    assert record is not None
    assert record.owner_identity == "repo-owner"
    assert record.timestamp == NOW
    assert record.note == "Checked live"
    assert record.task_revision == "task-r3"
    assert record.verification_evidence_ref == "pytest:workspace-green"
    assert record.source_revision == "source-r9"
    assert result.progress == 100


def test_stale_agent_is_exposed_in_overview():
    agent = AgentWorkspaceView(
        id="agent-1",
        name="Codex",
        task="task-1",
        status="active",
        progress=40,
        direction_revision="master-r0",
        ack_revision="master-r0",
        stale=True,
        blockers=("direction changed",),
    )
    overview = make_service(
        RecordingTaskSource(), agent_source=StaticAgentSource([agent])
    ).get_overview()
    assert overview.agents[0].stale is True
    assert overview.agents[0].blockers == ("direction changed",)


def test_empty_sources_produce_valid_empty_overview_without_fake_tasks():
    service = WorkspaceService(
        agent_source=EmptyAgentSource(),
        checkpoint_source=EmptyCheckpointSource(),
        revision_source=StaticRevisionSource("master-empty"),
        clock=lambda: NOW,
    )
    overview = service.get_overview()
    payload = overview.to_dict()
    assert payload == {
        "master_revision": "master-empty",
        "updated_at": NOW,
        "agents": [],
        "tasks": [],
        "checkpoints": [],
    }


def test_approve_requires_complete_agent_verification_evidence():
    source = RecordingTaskSource([
        verified_task(agent_verified=False, verification_evidence_ref="")
    ])
    with pytest.raises(WorkspaceValidationError, match="agent verification"):
        make_service(source).record_owner_verification(
            "task-1", verified=True, note="Tried", owner_identity="owner",
        )


def test_approve_requires_source_revision():
    source = RecordingTaskSource([verified_task(source_revision="")])
    service = WorkspaceService(
        task_source=source,
        agent_source=EmptyAgentSource(),
        checkpoint_source=EmptyCheckpointSource(),
        revision_source=StaticRevisionSource(""),
        clock=lambda: NOW,
    )
    with pytest.raises(WorkspaceValidationError, match="source revision"):
        service.record_owner_verification(
            "task-1", verified=True, note="Checked", owner_identity="owner",
        )
