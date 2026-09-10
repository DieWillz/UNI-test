from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from uni.devcoord.workspace_models import (
    AgentSession,
    LeaseState,
    ResourceLease,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


class TakeoverRecord(BaseModel):
    takeover_id: str = Field(default_factory=lambda: str(uuid4()))
    stale_session_id: str
    task_id: str | None = None
    snapshot_ref: str
    prepared_at: str


class ControlledTakeover:
    """Prepare a stale session for safe ownership transfer."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
    def prepare(self, stale_session_id: str, snapshot_ref: str) -> TakeoverRecord:
        if not snapshot_ref.strip():
            raise ValueError("snapshot reference is required")
        session = self.store.get_session(stale_session_id)
        if session.state is not SessionState.STALE:
            raise ValueError("takeover requires a stale session")

        prepared_at = datetime.now(timezone.utc).isoformat()
        with self.store.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT lease_id, payload_json FROM resource_leases WHERE agent_session_id=? AND state!=?",
                (stale_session_id, LeaseState.RELEASED.value),
            ).fetchall()
            for lease_id, payload_json in rows:
                lease = ResourceLease.model_validate(json.loads(payload_json)).model_copy(
                    update={"state": LeaseState.RELEASED, "released_at": prepared_at}
                )
                conn.execute(
                    "UPDATE resource_leases SET state=?, payload_json=? WHERE lease_id=?",
                    (LeaseState.RELEASED.value, lease.model_dump_json(), lease_id),
                )
            stopped = session.model_copy(update={"state": SessionState.STOPPED})
            conn.execute(
                "UPDATE agent_sessions SET state=?, payload_json=? WHERE session_id=?",
                (SessionState.STOPPED.value, stopped.model_dump_json(), stale_session_id),
            )

        record = TakeoverRecord(
            stale_session_id=stale_session_id,
            task_id=session.task_id,
            snapshot_ref=snapshot_ref,
            prepared_at=prepared_at,
        )
        self.store.append_event(
            WorkspaceEvent(
                event="takeover.prepared",
                task_id=session.task_id,
                session_id=stale_session_id,
                detail=snapshot_ref,
            )
        )
        return record
