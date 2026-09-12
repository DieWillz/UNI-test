from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from uni.direction_sync import DirectionSyncError, DirectionSyncGate
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


class AgentCoordinationStatus(str, Enum):
    SYNC_REQUIRED = "SYNC_REQUIRED"
    READY = "READY"
    ACTIVE = "ACTIVE"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    STALE = "STALE"
    DONE = "DONE"


@dataclass(frozen=True)
class DirectionDecision:
    allowed: bool
    status: AgentCoordinationStatus
    reason: str
    revision: str | None
    stale: bool
    blockers: tuple[str, ...] = ()


class MawcDirectionCoordinator:
    """MAWC adapter around the project-wide DirectionSyncGate."""

    def __init__(self, store: WorkspaceStore, gate: DirectionSyncGate) -> None:
        self.store = store
        self.gate = gate

    @staticmethod
    def _task_paths(task: WorkspaceTask | None) -> list[str]:
        if task is None:
            return []
        return [
            item.resource_key
            for item in task.requested_resources
            if item.resource_type in {ResourceType.FILE, ResourceType.TREE}
        ]

    @staticmethod
    def _heartbeat_expired(session: AgentSession) -> bool:
        if not session.expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(session.expires_at)
        except ValueError:
            return True
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)
    def acknowledge(self, session_id: str) -> AgentSession:
        session = self.store.get_session(session_id)
        record = self.gate.acknowledge(session.display_name)
        synced = session.model_copy(update={
            "direction_revision_ack": record["revision"],
            "direction_synced_at": record.get("acknowledged_at") or utc_now(),
            "direction_stale": False,
        })
        with self.store.transaction(immediate=True) as conn:
            self.store.save_session(synced, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="direction.acknowledged",
                    task_id=synced.task_id,
                    session_id=synced.session_id,
                    detail=f"revision={record['revision']}",
                ),
                conn=conn,
            )
        return synced

    def evaluate(
        self,
        session: AgentSession,
        task: WorkspaceTask | None = None,
    ) -> DirectionDecision:
        try:
            check = self.gate.check(session.display_name, paths=self._task_paths(task))
        except (DirectionSyncError, OSError, ValueError) as exc:
            return DirectionDecision(
                False,
                AgentCoordinationStatus.BLOCKED,
                f"direction_sync_error:{exc}",
                None,
                False,
                (f"direction_sync_error:{exc}",),
            )

        if self._heartbeat_expired(session):
            return DirectionDecision(
                False, AgentCoordinationStatus.STALE, "heartbeat_expired",
                check.revision, True, ("heartbeat_expired",),
            )
        if session.state is SessionState.STALE:
            return DirectionDecision(
                False, AgentCoordinationStatus.STALE, "heartbeat_stale",
                check.revision, True, ("heartbeat_stale",),
            )
        if not check.ok:
            if check.reason == "stale_direction":
                status = AgentCoordinationStatus.STALE
                stale = True
            elif check.reason in {"not_acknowledged", "agent_not_assigned"}:
                status = AgentCoordinationStatus.SYNC_REQUIRED
                stale = False
            else:
                status = AgentCoordinationStatus.BLOCKED
                stale = False
            blockers = tuple([check.reason, *(
                f"{item.get('path', '')}:{item.get('owner', '')}"
                for item in check.conflicts
            )])
            return DirectionDecision(
                False, status, check.reason, check.revision, stale, blockers
            )

        if session.direction_revision_ack != check.revision:
            has_previous_ack = bool(session.direction_revision_ack)
            return DirectionDecision(
                False,
                AgentCoordinationStatus.STALE if has_previous_ack else AgentCoordinationStatus.SYNC_REQUIRED,
                "session_ack_mismatch",
                check.revision,
                has_previous_ack,
                ("session_ack_mismatch",),
            )

        if session.state is SessionState.VERIFYING:
            status = AgentCoordinationStatus.VERIFYING
        elif task is not None and task.state in {WorkTaskState.VERIFIED, WorkTaskState.MERGED}:
            status = AgentCoordinationStatus.DONE
        elif session.task_id:
            status = AgentCoordinationStatus.ACTIVE
        else:
            status = AgentCoordinationStatus.READY
        return DirectionDecision(True, status, "current", check.revision, False)

    def refresh(self, session_id: str) -> DirectionDecision:
        session = self.store.get_session(session_id)
        task = self.store.get_workspace_task(session.task_id) if session.task_id else None
        decision = self.evaluate(session, task)
        if session.direction_stale != decision.stale:
            updated = session.model_copy(update={"direction_stale": decision.stale})
            with self.store.transaction(immediate=True) as conn:
                self.store.save_session(updated, conn=conn)
                self.store.append_event(
                    WorkspaceEvent(
                        event="direction.stale" if decision.stale else "direction.current",
                        task_id=session.task_id,
                        session_id=session.session_id,
                        detail=decision.reason,
                    ),
                    conn=conn,
                )
        return decision

    @staticmethod
    def _progress(task: WorkspaceTask) -> dict[str, int | bool]:
        total = len(task.acceptance_items)
        passed = sum(1 for item in task.acceptance_items if item.passed)
        percent = int((passed * 100) / total) if total else 0
        confirmed = percent if task.owner_verified else min(percent, 99)
        return {
            "passed": passed,
            "total": total,
            "percent": percent,
            "owner_verified": task.owner_verified,
            "user_confirmed_percent": confirmed,
        }

    def snapshot(self) -> dict[str, Any]:
        sessions = self.store.list_sessions()
        tasks = self.store.list_workspace_tasks()
        task_by_id = {task.id: task for task in tasks}
        leases = ResourceLeaseManager(self.store).list_active()
        progress = {task.id: self._progress(task) for task in tasks}
        agents: list[dict[str, Any]] = []
        revisions: list[str] = []
        blockers: list[dict[str, str]] = []
        updated_values = [task.updated_at for task in tasks]

        for session in sessions:
            task = task_by_id.get(session.task_id or "")
            decision = self.evaluate(session, task)
            if decision.revision:
                revisions.append(decision.revision)
            owned_paths = [
                lease.resource_key for lease in leases
                if lease.agent_session_id == session.session_id
                and lease.resource_type in {ResourceType.FILE, ResourceType.TREE}
            ]
            agent_progress = progress.get(task.id) if task is not None else {
                "passed": 0,
                "total": 0,
                "percent": 0,
                "owner_verified": False,
                "user_confirmed_percent": 0,
            }
            agents.append({
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "display_name": session.display_name,
                "direction_revision_ack": session.direction_revision_ack,
                "direction_synced_at": session.direction_synced_at,
                "last_heartbeat": session.heartbeat_at,
                "last_updated": session.heartbeat_at,
                "current_task": session.task_id,
                "progress": agent_progress,
                "owned_paths": sorted(set(owned_paths)),
                "status": decision.status.value,
                "stale": decision.stale or session.direction_stale,
                "blockers": list(decision.blockers),
            })
            updated_values.append(session.heartbeat_at)
            blockers.extend(
                {"session_id": session.session_id, "reason": item}
                for item in decision.blockers
            )

        assignments = [
            {
                "task_id": task.id,
                "session_id": task.assigned_session_id,
                "state": task.state.value,
            }
            for task in tasks if task.assigned_session_id
        ]
        stale = [item["session_id"] for item in agents if item["stale"]]
        return {
            "agents": agents,
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "assignments": assignments,
            "leases": [lease.model_dump(mode="json") for lease in leases],
            "progress": progress,
            "updated_at": max(updated_values) if updated_values else utc_now(),
            "direction_revision": revisions[0] if revisions else None,
            "ack_revision": {
                session.session_id: session.direction_revision_ack for session in sessions
            },
            "stale": stale,
            "blockers": blockers,
        }
