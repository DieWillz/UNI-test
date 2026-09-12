from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from uni.devcoord.lease_rules import normalize_resource_key
from uni.devcoord.workspace_models import (
    AgentSession,
    LeaseState,
    ResourceLease,
    ResourceType,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


def _runtime_expired(expires_at: str | None, moment: datetime) -> bool:
    if not expires_at:
        return False
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= moment


class WorkspaceSummary(BaseModel):
    active_sessions: int = 0
    stale_sessions: int = 0
    active_leases: int = 0
    stale_leases: int = 0
    conflict_events: int = 0
    unowned_changes: int = 0


class WorkspaceStatus:
    """Read-only objective status queries over MAWC SQLite state."""

    _ACTIVE_LEASE_STATES = {
        LeaseState.CLAIMED.value,
        LeaseState.ACTIVE.value,
        LeaseState.VERIFYING.value,
    }
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def summary(self) -> WorkspaceSummary:
        moment = datetime.now(timezone.utc)
        with self.store.transaction() as conn:
            session_rows = conn.execute(
                "SELECT payload_json FROM agent_sessions"
            ).fetchall()
            lease_rows = conn.execute(
                "SELECT payload_json FROM resource_leases WHERE state!=?",
                (LeaseState.RELEASED.value,),
            ).fetchall()
        sessions = [AgentSession.model_validate_json(row[0]) for row in session_rows]
        leases = [ResourceLease.model_validate_json(row[0]) for row in lease_rows]
        active_sessions = sum(
            item.state in {SessionState.ACTIVE, SessionState.VERIFYING}
            and not _runtime_expired(item.expires_at, moment) for item in sessions
        )
        stale_sessions = sum(
            item.state is SessionState.STALE
            or (item.state is not SessionState.STOPPED and _runtime_expired(item.expires_at, moment))
            for item in sessions
        )
        active_leases = sum(
            item.state.value in self._ACTIVE_LEASE_STATES
            and not _runtime_expired(item.expires_at, moment) for item in leases
        )
        stale_leases = sum(
            item.state is LeaseState.STALE or _runtime_expired(item.expires_at, moment)
            for item in leases
        )
        events = self.store.list_events(limit=5000)
        return WorkspaceSummary(
            active_sessions=active_sessions,
            stale_sessions=stale_sessions,
            active_leases=active_leases,
            stale_leases=stale_leases,
            conflict_events=sum(event.event == "lease.conflict" for event in events),
            unowned_changes=sum(
                event.event == "workspace.unowned_change" for event in events
            ),
        )
    def resource(
        self,
        resource_type: ResourceType,
        resource_key: str,
    ) -> list[ResourceLease]:
        normalized = normalize_resource_key(resource_type, resource_key)
        with self.store.transaction() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM resource_leases
                WHERE resource_type=? AND resource_key=? AND state!=?
                ORDER BY rowid
                """,
                (resource_type.value, normalized, LeaseState.RELEASED.value),
            ).fetchall()
        return [ResourceLease.model_validate_json(row[0]) for row in rows]

    def events(self, *, limit: int = 100) -> list[WorkspaceEvent]:
        if limit < 1:
            raise ValueError("limit must be positive")
        return self.store.list_events(limit=limit)