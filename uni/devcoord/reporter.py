from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from uni.devcoord.workspace_store import WorkspaceStore


class DevelopmentReport(BaseModel):
    session_counts: dict[str, int] = Field(default_factory=dict)
    task_counts: dict[str, int] = Field(default_factory=dict)
    lease_counts: dict[str, int] = Field(default_factory=dict)
    conflict_events: int = 0
    unowned_changes: int = 0
    ownership_violations: int = 0
    critical_events: int = 0


class DevelopmentReporter:
    """Build objective MAWC reports from persisted coordinator state only."""

    _CRITICAL_EVENTS = {
        "workspace.unowned_change",
        "workspace.ownership_violation",
        "session.recovery_failed",
        "merge.conflict",
        "supervisor.failure",
    }

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def snapshot(self) -> DevelopmentReport:
        with self.store.transaction() as conn:
            session_rows = conn.execute(
                "SELECT state FROM agent_sessions"
            ).fetchall()
            task_rows = conn.execute(
                "SELECT state FROM workspace_tasks"
            ).fetchall()
            lease_rows = conn.execute(
                "SELECT state FROM resource_leases"
            ).fetchall()

        events = self.store.list_events(limit=5000)
        session_counts = Counter(str(row[0]) for row in session_rows)
        task_counts = Counter(str(row[0]) for row in task_rows)
        lease_counts = Counter(str(row[0]) for row in lease_rows)

        return DevelopmentReport(
            session_counts=dict(session_counts),
            task_counts=dict(task_counts),
            lease_counts=dict(lease_counts),
            conflict_events=sum(event.event == "task.conflict" for event in events),
            unowned_changes=sum(
                event.event == "workspace.unowned_change" for event in events
            ),
            ownership_violations=sum(
                event.event == "workspace.ownership_violation" for event in events
            ),
            critical_events=sum(
                event.event in self._CRITICAL_EVENTS for event in events
            ),
        )
