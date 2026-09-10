from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from uni.devcoord.lease_rules import normalize_resource_key, resources_overlap
from uni.devcoord.workspace_models import (
    AccessMode,
    LeaseState,
    ResourceLease,
    ResourceRequest,
)
from uni.devcoord.workspace_store import WorkspaceStore


class LeaseConflictError(RuntimeError):
    def __init__(self, conflicts: list[ResourceLease]) -> None:
        self.conflicts = conflicts
        summary = ", ".join(
            f"{item.resource_type.value}:{item.resource_key} owned by {item.agent_session_id}"
            for item in conflicts
        )
        super().__init__(f"resource lease conflict: {summary}")


class ResourceLeaseManager:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    @staticmethod
    def _expires_at(ttl_seconds: float) -> tuple[str, str]:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        return now.isoformat(), expires.isoformat()

    @staticmethod
    def _load_lease(payload: str) -> ResourceLease:
        return ResourceLease.model_validate(json.loads(payload))

    def _blocking_write_leases(self, conn) -> list[ResourceLease]:
        rows = conn.execute(
            """
            SELECT payload_json FROM resource_leases
            WHERE access_mode=? AND state!=?
            """,
            (AccessMode.WRITE.value, LeaseState.RELEASED.value),
        ).fetchall()
        return [self._load_lease(row[0]) for row in rows]

    def claim(
        self,
        task_id: str,
        session_id: str,
        resources: list[ResourceRequest],
        ttl_seconds: float = 600.0,
    ) -> list[ResourceLease]:
        if not resources:
            raise ValueError("resources must not be empty")
        heartbeat_at, expires_at = self._expires_at(ttl_seconds)

        normalized = [
            request.model_copy(
                update={"resource_key": normalize_resource_key(request.resource_type, request.resource_key)}
            )
            for request in resources
        ]
        with self.store.transaction(immediate=True) as conn:
            existing = self._blocking_write_leases(conn)
            conflicts: list[ResourceLease] = []
            for request in normalized:
                if request.access_mode is not AccessMode.WRITE:
                    continue
                for lease in existing:
                    if resources_overlap(
                        request.resource_type,
                        request.resource_key,
                        lease.resource_type,
                        lease.resource_key,
                    ):
                        conflicts.append(lease)
            if conflicts:
                unique = {item.lease_id: item for item in conflicts}
                raise LeaseConflictError(list(unique.values()))

            leases = [
                ResourceLease(
                    task_id=task_id,
                    agent_session_id=session_id,
                    resource_type=request.resource_type,
                    resource_key=request.resource_key,
                    access_mode=request.access_mode,
                    state=LeaseState.CLAIMED,
                    heartbeat_at=heartbeat_at,
                    expires_at=expires_at,
                )
                for request in normalized
            ]
            for lease in leases:
                conn.execute(
                    """
                    INSERT INTO resource_leases(
                        lease_id, task_id, agent_session_id, resource_type,
                        resource_key, access_mode, state, heartbeat_at,
                        expires_at, payload_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease.lease_id,
                        lease.task_id,
                        lease.agent_session_id,
                        lease.resource_type.value,
                        lease.resource_key,
                        lease.access_mode.value,
                        lease.state.value,
                        lease.heartbeat_at,
                        lease.expires_at,
                        lease.model_dump_json(),
                    ),
                )
        return leases

    def list_active(self) -> list[ResourceLease]:
        with self.store.transaction() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM resource_leases WHERE state!=? ORDER BY rowid",
                (LeaseState.RELEASED.value,),
            ).fetchall()
        return [self._load_lease(row[0]) for row in rows]

    def release(self, lease_id: str, *, current_hash: str | None = None) -> ResourceLease:
        released_at = datetime.now(timezone.utc).isoformat()
        with self.store.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload_json FROM resource_leases WHERE lease_id=?",
                (lease_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown resource lease: {lease_id}")
            lease = self._load_lease(row[0]).model_copy(
                update={
                    "state": LeaseState.RELEASED,
                    "current_hash": current_hash,
                    "released_at": released_at,
                }
            )
            conn.execute(
                """
                UPDATE resource_leases
                SET state=?, payload_json=?
                WHERE lease_id=?
                """,
                (LeaseState.RELEASED.value, lease.model_dump_json(), lease_id),
            )
        return lease
