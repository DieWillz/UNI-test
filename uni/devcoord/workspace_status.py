from __future__ import annotations

from pydantic import BaseModel

from uni.devcoord.lease_rules import normalize_resource_key
from uni.devcoord.workspace_models import (
    LeaseState,
    ResourceLease,
    ResourceType,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


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
        with self.store.transaction() as conn:
            session_rows = conn.execute(
                "SELECT state, COUNT(*) FROM agent_sessions GROUP BY state"
            ).fetchall()
            lease_rows = conn.execute(
                "SELECT state, COUNT(*) FROM resource_leases GROUP BY state"
            ).fetchall()
        sessions = {str(state): int(count) for state, count in session_rows}
        leases = {str(state): int(count) for state, count in lease_rows}
        events = self.store.list_events(limit=5000)
        return WorkspaceSummary(
            active_sessions=(
                sessions.get(SessionState.ACTIVE.value, 0)
                + sessions.get(SessionState.VERIFYING.value, 0)
            ),
            stale_sessions=sessions.get(SessionState.STALE.value, 0),
            active_leases=sum(leases.get(state, 0) for state in self._ACTIVE_LEASE_STATES),
            stale_leases=leases.get(LeaseState.STALE.value, 0),
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