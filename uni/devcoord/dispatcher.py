from __future__ import annotations

from dataclasses import dataclass

from uni.devcoord.direction_gate import MawcDirectionCoordinator
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.models import utc_now
from uni.devcoord.scheduler import DispatchAssignment, TaskScheduler
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceLease,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
from uni.devcoord.workspace_store import WorkspaceStore
from uni.devcoord.worktrees import WorktreeManager, WorktreeRef


@dataclass(frozen=True)
class PreparedDispatch:
    task: WorkspaceTask
    leases: list[ResourceLease]
    worktree: WorktreeRef
    session: AgentSession


class TaskDispatcher:
    """Bind a scheduler reservation to an isolated task worktree and session."""

    def __init__(
        self,
        store: WorkspaceStore,
        worktrees: WorktreeManager,
        *,
        direction_sync: MawcDirectionCoordinator | None = None,
    ) -> None:
        self.store = store
        self.worktrees = worktrees
        self.scheduler = TaskScheduler(store, direction_sync=direction_sync)
        self.leases = ResourceLeaseManager(store)

    def prepare(
        self,
        session_id: str,
        *,
        base_ref: str = "HEAD",
        ttl_seconds: float = 600.0,
    ) -> PreparedDispatch | None:
        assignment = self.scheduler.reserve_next(session_id, ttl_seconds=ttl_seconds)
        if assignment is None:
            return None

        session = self.store.get_session(session_id)
        try:
            worktree = self.worktrees.create(
                session.agent_id,
                assignment.task.id,
                base_ref=base_ref,
            )
        except Exception as exc:
            self._rollback_reservation(assignment, session_id, exc)
            raise

        bound = session.model_copy(
            update={
                "task_id": assignment.task.id,
                "worktree_path": str(worktree.path),
            }
        )
        try:
            with self.store.transaction(immediate=True) as conn:
                self.store.save_session(bound, conn=conn)
                self.store.append_event(
                    WorkspaceEvent(
                        event="dispatch.prepared",
                        task_id=assignment.task.id,
                        session_id=session_id,
                        detail=f"worktree={worktree.path}",
                    ),
                    conn=conn,
                )
        except Exception as exc:
            cleanup_error = self._discard_worktree(worktree)
            self._rollback_reservation(assignment, session_id, exc)
            if cleanup_error is not None:
                exc.add_note(f"worktree cleanup failed: {cleanup_error}")
            raise
        return PreparedDispatch(
            task=assignment.task,
            leases=assignment.leases,
            worktree=worktree,
            session=bound,
        )

    def _discard_worktree(self, worktree: WorktreeRef) -> Exception | None:
        try:
            self.worktrees.discard(worktree)
        except Exception as exc:
            return exc
        return None

    def _rollback_reservation(
        self,
        assignment: DispatchAssignment,
        session_id: str,
        error: Exception,
    ) -> None:
        for lease in assignment.leases:
            self.leases.release(lease.lease_id)

        fresh = self.store.get_workspace_task(assignment.task.id)
        if (
            fresh.state is WorkTaskState.CLAIMED
            and fresh.assigned_session_id == session_id
        ):
            restored = fresh.model_copy(
                update={
                    "state": WorkTaskState.READY,
                    "assigned_session_id": None,
                    "updated_at": utc_now(),
                }
            )
            self.store.save_workspace_task(restored)
        self.store.append_event(
            WorkspaceEvent(
                event="dispatch.failed",
                task_id=assignment.task.id,
                session_id=session_id,
                detail=f"{type(error).__name__}: {error}",
            )
        )
