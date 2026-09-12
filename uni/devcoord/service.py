from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json

from uni.devcoord.direction_gate import MawcDirectionCoordinator
from uni.devcoord.lease_rules import access_mode_can_write, normalize_resource_key, resources_overlap
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.models import utc_now
from uni.devcoord.reporter import DevelopmentReporter
from uni.devcoord.scheduler import TaskScheduler
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.takeover import ControlledTakeover
from uni.devcoord.workspace_monitor import WorkspaceMonitor
from uni.devcoord.workspace_models import (
    AgentSession,
    ResourceRequest,
    ResourceType,
    SessionState,
    WorkTaskState,
    WorkspaceEvent,
    WorkspaceTask,
)
from uni.devcoord.workspace_status import WorkspaceStatus
from uni.devcoord.workspace_store import WorkspaceStore


class DevelopmentCoordinatorService:
    """Reusable owner/runtime facade over the existing MAWC components."""

    def __init__(
        self,
        store: WorkspaceStore,
        *,
        direction_sync: MawcDirectionCoordinator | None = None,
    ) -> None:
        self.store = store
        self.direction_sync = direction_sync
        self.scheduler = TaskScheduler(store, direction_sync=direction_sync)

    def _session(self, agent_or_session_id: str) -> AgentSession:
        try:
            return self.store.get_session(agent_or_session_id)
        except KeyError:
            matches = [
                session for session in self.store.list_sessions()
                if session.agent_id == agent_or_session_id
            ]
        if not matches:
            raise KeyError(f"unknown agent/session: {agent_or_session_id}")
        matches.sort(key=lambda item: item.heartbeat_at, reverse=True)
        return matches[0]

    def _task(self, task_id: str) -> WorkspaceTask:
        return self.store.get_workspace_task(task_id)

    @staticmethod
    def _dump(items) -> list[dict]:
        return [item.model_dump(mode="json") for item in items]

    def development_status(self) -> dict:
        summary = WorkspaceStatus(self.store).summary().model_dump(mode="json")
        report = DevelopmentReporter(self.store).snapshot().model_dump(mode="json")
        sessions = self.store.list_sessions()
        tasks = self.store.list_workspace_tasks()
        leases = ResourceLeaseManager(self.store).list_active()
        events = self.store.list_events(limit=100)
        conflicts = [
            event for event in events
            if "conflict" in event.event
        ]
        coordination = self.direction_sync.snapshot() if self.direction_sync else None
        return {
            "summary": summary,
            "coordination": coordination,
            "report": report,
            "agents": self._dump(sessions),
            "tasks": self._dump(tasks),
            "leases": self._dump(leases),
            "conflicts": self._dump(conflicts),
            "events": self._dump(events),
            "owner_intervention": bool(
                summary.get("stale_sessions")
                or summary.get("unowned_changes")
                or report.get("critical_events")
            ),
        }

    def inspect_file_owner(self, path: str) -> dict:
        normalized = normalize_resource_key(ResourceType.FILE, path)
        owners: list[dict] = []
        for lease in ResourceLeaseManager(self.store).list_active():
            if not access_mode_can_write(lease.access_mode):
                continue
            if not resources_overlap(
                ResourceType.FILE, normalized, lease.resource_type, lease.resource_key
            ):
                continue
            try:
                agent_id = self.store.get_session(lease.agent_session_id).agent_id
            except KeyError:
                agent_id = lease.agent_session_id
            owners.append({
                "agent_id": agent_id,
                "session_id": lease.agent_session_id,
                "task_id": lease.task_id,
                "lease_id": lease.lease_id,
                "resource_type": lease.resource_type.value,
                "resource_key": lease.resource_key,
                "access_mode": lease.access_mode.value,
                "state": lease.state.value,
                "expires_at": lease.expires_at,
            })
        return {"path": normalized, "owned": bool(owners), "owners": owners}

    def pause_agent(self, agent_or_session_id: str) -> AgentSession:
        session_id = self._session(agent_or_session_id).session_id
        with self.store.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown agent session: {session_id}")
            session = AgentSession.model_validate(json.loads(row[0]))
            active_lease = conn.execute(
                "SELECT 1 FROM resource_leases WHERE agent_session_id=? AND state!='released' LIMIT 1",
                (session_id,),
            ).fetchone()
            if session.task_id is not None or session.process_id is not None or active_lease is not None:
                raise RuntimeError("only an idle agent session can be paused")
            paused = session.model_copy(update={"state": SessionState.STOPPED})
            self.store.save_session(paused, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="agent.paused",
                    task_id=paused.task_id,
                    session_id=paused.session_id,
                    detail=f"agent_id={paused.agent_id}",
                ),
                conn=conn,
            )
        return paused

    def resume_agent(self, agent_or_session_id: str) -> AgentSession:
        session = self._session(agent_or_session_id)
        if session.state is SessionState.STALE:
            raise RuntimeError("stale agent requires controlled takeover before resume")
        now = datetime.now(timezone.utc)
        resumed = session.model_copy(update={
            "state": SessionState.ACTIVE,
            "heartbeat_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=600)).isoformat(),
        })
        with self.store.transaction(immediate=True) as conn:
            self.store.save_session(resumed, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="agent.resumed",
                    task_id=resumed.task_id,
                    session_id=resumed.session_id,
                    detail=f"agent_id={resumed.agent_id}",
                ),
                conn=conn,
            )
        return resumed

    def prioritize_task(self, task_id: str, priority: int) -> WorkspaceTask:
        task = self._task(task_id)
        updated = task.model_copy(update={"priority": priority, "updated_at": utc_now()})
        with self.store.transaction(immediate=True) as conn:
            self.store.save_workspace_task(updated, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="task.prioritized", task_id=task_id, detail=f"priority={priority}"
                ),
                conn=conn,
            )
        return updated

    def pause_task(self, task_id: str) -> WorkspaceTask:
        with self.store.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload_json FROM workspace_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown workspace task: {task_id}")
            task = WorkspaceTask.model_validate(json.loads(row[0]))
            if task.state not in {WorkTaskState.PLANNED, WorkTaskState.READY}:
                raise RuntimeError(
                    f"only queued tasks can be paused; current state is {task.state.value}"
                )
            updated = task.model_copy(
                update={"state": WorkTaskState.BLOCKED, "updated_at": utc_now()}
            )
            self.store.save_workspace_task(updated, conn=conn)
            self.store.append_event(
                WorkspaceEvent(event="task.paused", task_id=task_id), conn=conn
            )
        return updated

    def resume_task(self, task_id: str) -> WorkspaceTask:
        task = self._task(task_id)
        if task.state is not WorkTaskState.BLOCKED:
            raise RuntimeError("only BLOCKED tasks can be resumed")
        updated = task.model_copy(
            update={"state": WorkTaskState.READY, "updated_at": utc_now()}
        )
        with self.store.transaction(immediate=True) as conn:
            self.store.save_workspace_task(updated, conn=conn)
            self.store.append_event(
                WorkspaceEvent(event="task.resumed", task_id=task_id), conn=conn
            )
        return updated

    def release_lease(self, lease_id: str):
        manager = ResourceLeaseManager(self.store)
        with self.store.transaction(immediate=True) as conn:
            item = manager.release(lease_id, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="lease.released",
                    task_id=item.task_id,
                    session_id=item.agent_session_id,
                    lease_id=item.lease_id,
                    resource_type=item.resource_type,
                    resource_key=item.resource_key,
                ),
                conn=conn,
            )
        return item

    def list_agents(self) -> list[dict]:
        return self._dump(self.store.list_sessions())

    def list_tasks(self) -> list[dict]:
        return self._dump(self.store.list_workspace_tasks())

    def list_leases(self) -> list[dict]:
        return self._dump(ResourceLeaseManager(self.store).list_active())

    def list_conflicts(self) -> list[dict]:
        return self._dump([
            event for event in self.store.list_events(limit=5000)
            if "conflict" in event.event
        ])

    def inspect_agent(self, agent_or_session_id: str) -> dict:
        session = self._session(agent_or_session_id)
        leases = [
            lease for lease in ResourceLeaseManager(self.store).list_active()
            if lease.agent_session_id == session.session_id
        ]
        task = self._task(session.task_id) if session.task_id else None
        return {
            "session": session.model_dump(mode="json"),
            "task": task.model_dump(mode="json") if task else None,
            "leases": self._dump(leases),
        }

    def inspect_task(self, task_id: str) -> dict:
        task = self._task(task_id)
        session = (
            self.store.get_session(task.assigned_session_id)
            if task.assigned_session_id else None
        )
        leases = [
            lease for lease in ResourceLeaseManager(self.store).list_active()
            if lease.task_id == task_id
        ]
        events = [
            event for event in self.store.list_events(limit=5000)
            if event.task_id == task_id
        ]
        return {
            "task": task.model_dump(mode="json"),
            "session": session.model_dump(mode="json") if session else None,
            "leases": self._dump(leases),
            "events": self._dump(events),
        }

    def assign_task(self, task_id: str, session_id: str, *, ttl_seconds: float = 600.0) -> dict:
        eligible = {task.id: task for task in self.scheduler.ready_tasks(session_id)}
        if task_id not in eligible:
            raise RuntimeError("task is not eligible for this session")

        manager = ResourceLeaseManager(self.store)
        with self.store.transaction(immediate=True) as conn:
            session = self.store.get_session(session_id, conn=conn)
            if session.state is not SessionState.ACTIVE:
                raise RuntimeError("target session must be ACTIVE")
            if session.task_id is not None or session.process_id is not None:
                raise RuntimeError("target session must be idle")
            fresh = self.store.get_workspace_task(task_id, conn=conn)
            if fresh.state not in {WorkTaskState.PLANNED, WorkTaskState.READY}:
                raise RuntimeError(f"task state changed to {fresh.state.value}")
            if not set(fresh.required_capabilities).issubset(set(session.capabilities)):
                raise RuntimeError("target session lacks required capabilities")
            for dependency in fresh.dependencies:
                if self.store.get_workspace_task(dependency, conn=conn).state is not WorkTaskState.MERGED:
                    raise RuntimeError("task dependencies are not merged")
            if self.direction_sync is not None:
                decision = self.direction_sync.evaluate(session, fresh)
                if not decision.allowed:
                    raise RuntimeError(f"direction sync blocks assignment: {decision.reason}")
            resources = [
                ResourceRequest(resource_type=ResourceType.GLOBAL, resource_key=f"task:{fresh.id}"),
                *fresh.requested_resources,
            ]
            leases = manager.claim(
                fresh.id, session_id, resources, ttl_seconds=ttl_seconds, conn=conn
            )
            claimed = fresh.model_copy(update={
                "state": WorkTaskState.CLAIMED,
                "assigned_session_id": session_id,
                "updated_at": utc_now(),
            })
            self.store.save_workspace_task(claimed, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="task.assigned", task_id=task_id, session_id=session_id,
                    detail=f"leases={len(leases)}",
                ),
                conn=conn,
            )
        return {
            "task": claimed.model_dump(mode="json"),
            "leases": self._dump(leases),
        }

    def assign_next(self, session_id: str, *, ttl_seconds: float = 600.0) -> dict | None:
        assignment = self.scheduler.reserve_next(session_id, ttl_seconds=ttl_seconds)
        if assignment is None:
            return None
        return {
            "task": assignment.task.model_dump(mode="json"),
            "leases": self._dump(assignment.leases),
        }

    def acknowledge_direction(self, session_id: str) -> AgentSession:
        if self.direction_sync is None:
            raise RuntimeError("direction sync is not configured")
        return self.direction_sync.acknowledge(session_id)

    def heartbeat(self, session_id: str, *, ttl_seconds: float = 600.0) -> AgentSession:
        return AgentSessionManager(self.store).heartbeat(
            session_id, ttl_seconds=ttl_seconds
        )

    def can_write(self, agent_id: str, path: str) -> dict:
        return asdict(WorkspaceMonitor(self.store).can_write(agent_id, path))

    def audit_paths(
        self, paths: list[str], *, expected_session_id: str | None = None
    ) -> list[dict]:
        return [
            asdict(item) for item in WorkspaceMonitor(self.store).audit_paths(
                paths, expected_session_id=expected_session_id
            )
        ]

    def stop_agent(self, agent_or_session_id: str) -> AgentSession:
        """Stop an idle session without destroying any active work."""
        stopped = self.pause_agent(agent_or_session_id)
        self.store.append_event(
            WorkspaceEvent(
                event="agent.stopped",
                task_id=stopped.task_id,
                session_id=stopped.session_id,
                detail=f"agent_id={stopped.agent_id}",
            )
        )
        return stopped

    def force_takeover(self, stale_session_id: str, snapshot_ref: str) -> dict:
        """Release a STALE session only after its work has been snapshotted."""
        record = ControlledTakeover(self.store).prepare(stale_session_id, snapshot_ref)
        return record.model_dump(mode="json")

    def reassign_task(
        self, task_id: str, session_id: str, *, ttl_seconds: float = 600.0
    ) -> dict:
        """Atomically move a not-yet-running claimed task to another session."""
        target = self.store.get_session(session_id)
        if target.state is not SessionState.ACTIVE:
            raise RuntimeError("target session must be ACTIVE")
        if target.task_id is not None or target.process_id is not None:
            raise RuntimeError("target session must be idle")
        task = self._task(task_id)
        if self.direction_sync is not None:
            decision = self.direction_sync.evaluate(target, task)
            if not decision.allowed:
                raise RuntimeError(f"direction sync blocks reassignment: {decision.reason}")
        if not set(task.required_capabilities).issubset(set(target.capabilities)):
            raise RuntimeError("target session lacks required capabilities")
        if any(self._task(dep).state is not WorkTaskState.MERGED for dep in task.dependencies):
            raise RuntimeError("task dependencies are not merged")
        if task.state in {WorkTaskState.PLANNED, WorkTaskState.READY}:
            return self.assign_task(task_id, session_id, ttl_seconds=ttl_seconds)
        if task.state is not WorkTaskState.CLAIMED:
            raise RuntimeError(
                f"only queued or CLAIMED tasks can be reassigned; current state={task.state.value}"
            )
        if not task.assigned_session_id:
            raise RuntimeError("claimed task has no assigned session")
        previous = self.store.get_session(task.assigned_session_id)
        if previous.process_id is not None or previous.state is SessionState.VERIFYING:
            raise RuntimeError("cannot reassign a running or verifying task")

        manager = ResourceLeaseManager(self.store)
        resources = [
            ResourceRequest(resource_type=ResourceType.GLOBAL, resource_key=f"task:{task.id}"),
            *task.requested_resources,
        ]
        with self.store.transaction(immediate=True) as conn:
            lease_rows = conn.execute(
                "SELECT lease_id FROM resource_leases WHERE task_id=? AND state!='released'",
                (task_id,),
            ).fetchall()
            for row in lease_rows:
                manager.release(str(row[0]), conn=conn)

            leases = manager.claim(
                task_id, session_id, resources, ttl_seconds=ttl_seconds, conn=conn
            )
            moved = task.model_copy(update={
                "state": WorkTaskState.CLAIMED,
                "assigned_session_id": session_id,
                "updated_at": utc_now(),
            })
            self.store.save_workspace_task(moved, conn=conn)
            if previous.task_id == task_id:
                self.store.save_session(
                    previous.model_copy(update={"task_id": None, "worktree_path": None}),
                    conn=conn,
                )
            self.store.append_event(
                WorkspaceEvent(
                    event="task.reassigned",
                    task_id=task_id,
                    session_id=session_id,
                    detail=f"from={previous.session_id}; leases={len(leases)}",
                ),
                conn=conn,
            )

        return {
            "task": moved.model_dump(mode="json"),
            "leases": self._dump(leases),
            "previous_session_id": previous.session_id,
        }
