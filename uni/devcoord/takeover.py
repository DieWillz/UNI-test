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
        prepared_at = datetime.now(timezone.utc).isoformat()
        with self.store.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?",
                (stale_session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown agent session: {stale_session_id}")
            session = AgentSession.model_validate(json.loads(row[0]))
            if session.state is not SessionState.STALE:
                raise ValueError("takeover requires a stale session")

            rows = conn.execute(
                "SELECT payload_json FROM resource_leases WHERE agent_session_id=? AND state!=?",
                (stale_session_id, LeaseState.RELEASED.value),
            ).fetchall()
            for lease_row in rows:
                lease = ResourceLease.model_validate(json.loads(lease_row[0])).model_copy(
                    update={"state": LeaseState.RELEASED, "released_at": prepared_at}
                )
                self.store.save_resource_lease(lease, conn=conn)
            stopped = session.model_copy(update={"state": SessionState.STOPPED})
            self.store.save_session(stopped, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="takeover.prepared",
                    task_id=session.task_id,
                    session_id=stale_session_id,
                    detail=snapshot_ref,
                ),
                conn=conn,
            )

        return TakeoverRecord(
            stale_session_id=stale_session_id,
            task_id=session.task_id,
            snapshot_ref=snapshot_ref,
            prepared_at=prepared_at,
        )
