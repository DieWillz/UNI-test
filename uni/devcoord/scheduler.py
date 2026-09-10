from __future__ import annotations

from dataclasses import dataclass

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

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def ready_tasks(self, session_id: str) -> list[WorkspaceTask]:
        session = self.store.get_session(session_id)
        if session.state is not SessionState.ACTIVE:
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
            resources = [
                ResourceRequest(
                    resource_type=ResourceType.GLOBAL,
                    resource_key=f"task:{candidate.id}",
                ),
                *candidate.requested_resources,
            ]
            try:
                leases = lease_manager.claim(
                    candidate.id,
                    session_id,
                    resources,
                    ttl_seconds=ttl_seconds,
                )
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

            try:
                fresh = self.store.get_workspace_task(candidate.id)
                if fresh.state not in {WorkTaskState.PLANNED, WorkTaskState.READY}:
                    for lease in leases:
                        lease_manager.release(lease.lease_id)
                    continue

                claimed = fresh.model_copy(
                    update={
                        "state": WorkTaskState.CLAIMED,
                        "assigned_session_id": session_id,
                        "updated_at": utc_now(),
                    }
                )
                self.store.save_workspace_task(claimed)
                self.store.append_event(
                    WorkspaceEvent(
                        event="task.claimed",
                        task_id=claimed.id,
                        session_id=session_id,
                        detail=f"leases={len(leases)}",
                    )
                )
                return DispatchAssignment(task=claimed, leases=leases)
            except Exception:
                for lease in leases:
                    try:
                        lease_manager.release(lease.lease_id)
                    except Exception:
                        pass
                raise

        return None
