from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from uni.devcoord.lease_rules import access_modes_conflict, normalize_resource_key, resources_overlap
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

    @staticmethod
    def _normalize_requests(resources: list[ResourceRequest]) -> list[ResourceRequest]:
        strength = {AccessMode.READ: 0, AccessMode.WRITE: 1, AccessMode.EXCLUSIVE: 2}
        merged: dict[tuple[object, str], ResourceRequest] = {}
        for request in resources:
            normalized = request.model_copy(
                update={"resource_key": normalize_resource_key(request.resource_type, request.resource_key)}
            )
            identity = (normalized.resource_type, normalized.resource_key)
            previous = merged.get(identity)
            if previous is None or strength[normalized.access_mode] > strength[previous.access_mode]:
                merged[identity] = normalized
        return list(merged.values())

    def _active_leases(self, conn) -> list[ResourceLease]:
        rows = conn.execute(
            "SELECT payload_json FROM resource_leases WHERE state!=?",
            (LeaseState.RELEASED.value,),
        ).fetchall()
        return [self._load_lease(row[0]) for row in rows]

    def claim(
        self,
        task_id: str,
        session_id: str,
        resources: list[ResourceRequest],
        ttl_seconds: float = 600.0,
        *,
        conn=None,
    ) -> list[ResourceLease]:
        if not resources:
            raise ValueError("resources must not be empty")
        if conn is None:
            with self.store.transaction(immediate=True) as transaction:
                return self.claim(
                    task_id, session_id, resources, ttl_seconds=ttl_seconds, conn=transaction
                )

        heartbeat_at, expires_at = self._expires_at(ttl_seconds)
        normalized = self._normalize_requests(resources)
        existing = self._active_leases(conn)
        reusable_states = {
            LeaseState.CLAIMED, LeaseState.ACTIVE, LeaseState.VERIFYING, LeaseState.HANDOFF
        }
        resolved: dict[tuple[object, str], ResourceLease] = {}
        pending: list[ResourceRequest] = []
        upgrades: dict[tuple[object, str], ResourceLease] = {}
        strength = {AccessMode.READ: 0, AccessMode.WRITE: 1, AccessMode.EXCLUSIVE: 2}
        for request in normalized:
            identity = (request.resource_type, request.resource_key)
            owned = next((
                lease for lease in existing
                if lease.task_id == task_id
                and lease.agent_session_id == session_id
                and lease.resource_type is request.resource_type
                and lease.resource_key == request.resource_key
                and lease.state in reusable_states
            ), None)
            if owned is not None and strength[owned.access_mode] >= strength[request.access_mode]:
                resolved[identity] = owned
            else:
                pending.append(request)
                if owned is not None:
                    upgrades[identity] = owned

        conflicts: list[ResourceLease] = []
        for request in pending:
            identity = (request.resource_type, request.resource_key)
            owned = upgrades.get(identity)
            for lease in existing:
                if owned is not None and lease.lease_id == owned.lease_id:
                    continue
                if access_modes_conflict(request.access_mode, lease.access_mode) and resources_overlap(
                    request.resource_type,
                    request.resource_key,
                    lease.resource_type,
                    lease.resource_key,
                ):
                    conflicts.append(lease)
        if conflicts:
            unique = {item.lease_id: item for item in conflicts}
            raise LeaseConflictError(list(unique.values()))

        for request in pending:
            identity = (request.resource_type, request.resource_key)
            owned = upgrades.get(identity)
            if owned is None:
                continue
            upgraded = owned.model_copy(
                update={
                    "access_mode": request.access_mode,
                    "heartbeat_at": heartbeat_at,
                    "expires_at": expires_at,
                }
            )
            conn.execute(
                "UPDATE resource_leases SET access_mode=?, heartbeat_at=?, expires_at=?, payload_json=? WHERE lease_id=?",
                (request.access_mode.value, heartbeat_at, expires_at, upgraded.model_dump_json(), owned.lease_id),
            )
            resolved[identity] = upgraded

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
            for request in pending
            if (request.resource_type, request.resource_key) not in upgrades
        ]
        for lease in leases:
            self.store.save_resource_lease(lease, conn=conn)
            resolved[(lease.resource_type, lease.resource_key)] = lease
        return [resolved[(request.resource_type, request.resource_key)] for request in normalized]

    def list_active(self) -> list[ResourceLease]:
        with self.store.transaction() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM resource_leases WHERE state!=? ORDER BY rowid",
                (LeaseState.RELEASED.value,),
            ).fetchall()
        return [self._load_lease(row[0]) for row in rows]

    def release(
        self,
        lease_id: str,
        *,
        current_hash: str | None = None,
        conn=None,
    ) -> ResourceLease:
        if conn is None:
            with self.store.transaction(immediate=True) as transaction:
                return self.release(lease_id, current_hash=current_hash, conn=transaction)
        released_at = datetime.now(timezone.utc).isoformat()
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
        self.store.save_resource_lease(lease, conn=conn)
        return lease
