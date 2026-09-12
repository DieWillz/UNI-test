from __future__ import annotations

from dataclasses import dataclass

from uni.devcoord.direction_gate import AgentCoordinationStatus, MawcDirectionCoordinator
from uni.devcoord.leases import LeaseConflictError, ResourceLeaseManager
from uni.devcoord.models import utc_now
from uni.devcoord.workspace_models import (
    ResourceLease,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore


@dataclass(frozen=True)
class DispatchAssignment:
    task: WorkspaceTask
    leases: list[ResourceLease]


class TaskScheduler:
    """Select runnable MAWC tasks without performing execution side effects."""

    def __init__(
        self,
        store: WorkspaceStore,
        *,
        direction_sync: MawcDirectionCoordinator | None = None,
    ) -> None:
        self.store = store
        self.direction_sync = direction_sync

    def ready_tasks(self, session_id: str) -> list[WorkspaceTask]:
        session = self.store.get_session(session_id)
        if session.state is not SessionState.ACTIVE:
            return []
        if session.task_id is not None or session.process_id is not None:
            return []

        tasks = self.store.list_workspace_tasks()
        by_id = {task.id: task for task in tasks}
        capabilities = set(session.capabilities)
        candidates: list[WorkspaceTask] = []

        for task in tasks:
            if task.state not in {WorkTaskState.PLANNED, WorkTaskState.READY}:
                continue
            if not set(task.required_capabilities).issubset(capabilities):
                continue
            if any(
                dependency not in by_id
                or by_id[dependency].state is not WorkTaskState.MERGED
                for dependency in task.dependencies
            ):
                continue
            if self.direction_sync is not None:
                decision = self.direction_sync.evaluate(session, task)
                if not decision.allowed:
                    continue
            candidates.append(task)

        candidates.sort(key=lambda task: (-task.priority, task.created_at, task.id))
        return candidates

    def reserve_next(
        self,
        session_id: str,
        *,
        ttl_seconds: float = 600.0,
    ) -> DispatchAssignment | None:
        lease_manager = ResourceLeaseManager(self.store)
        for candidate in self.ready_tasks(session_id):
            try:
                with self.store.transaction(immediate=True) as conn:
                    session = self.store.get_session(session_id, conn=conn)
                    if session.state is not SessionState.ACTIVE:
                        return None
                    if session.task_id is not None or session.process_id is not None:
                        return None
                    fresh = self.store.get_workspace_task(candidate.id, conn=conn)
                    if fresh.state not in {WorkTaskState.PLANNED, WorkTaskState.READY}:
                        continue
                    if not set(fresh.required_capabilities).issubset(set(session.capabilities)):
                        continue
                    if self.direction_sync is not None:
                        decision = self.direction_sync.evaluate(session, fresh)
                        if not decision.allowed:
                            blocked = session.model_copy(
                                update={"direction_stale": decision.stale}
                            )
                            self.store.save_session(blocked, conn=conn)
                            self.store.append_event(
                                WorkspaceEvent(
                                    event="direction.assignment_blocked",
                                    task_id=fresh.id,
                                    session_id=session_id,
                                    detail=decision.reason,
                                ),
                                conn=conn,
                            )
                            if decision.status in {
                                AgentCoordinationStatus.SYNC_REQUIRED,
                                AgentCoordinationStatus.STALE,
                            }:
                                return None
                            continue
                        if session.direction_stale:
                            session = session.model_copy(update={"direction_stale": False})
                            self.store.save_session(session, conn=conn)
                    resources = [
                        ResourceRequest(
                            resource_type=ResourceType.GLOBAL,
                            resource_key=f"task:{fresh.id}",
                        ),
                        *fresh.requested_resources,
                    ]
                    leases = lease_manager.claim(
                        fresh.id,
                        session_id,
                        resources,
                        ttl_seconds=ttl_seconds,
                        conn=conn,
                    )
                    claimed = fresh.model_copy(
                        update={
                            "state": WorkTaskState.CLAIMED,
                            "assigned_session_id": session_id,
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.save_workspace_task(claimed, conn=conn)
                    self.store.append_event(
                        WorkspaceEvent(
                            event="task.claimed",
                            task_id=claimed.id,
                            session_id=session_id,
                            detail=f"leases={len(leases)}",
                        ),
                        conn=conn,
                    )
                return DispatchAssignment(task=claimed, leases=leases)
            except LeaseConflictError as exc:
                self.store.append_event(
                    WorkspaceEvent(
                        event="task.conflict",
                        task_id=candidate.id,
                        session_id=session_id,
                        detail=str(exc),
                    )
                )
                continue

        return None
