from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from uni.devcoord.lease_rules import (
    access_mode_can_write,
    normalize_resource_key,
    resources_overlap,
)
from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.workspace_models import (
    LeaseState,
    ResourceLease,
    ResourceType,
    WorkspaceEvent,
)
from uni.devcoord.workspace_status import _runtime_expired
from uni.devcoord.workspace_store import WorkspaceStore


class GuardDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"


@dataclass(frozen=True)
class GuardResult:
    decision: GuardDecision
    agent: str
    owner: str | None
    task_id: str | None
    resource: str
    lease_id: str | None
    reason: str
    expires_at: str | None


@dataclass(frozen=True)
class AuditFinding:
    path: str
    event: str
    detail: str
    lease_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None


class WorkspaceMonitor:
    """Pre-edit ownership guard and post-edit lease auditor."""

    _WRITABLE_STATES = {
        LeaseState.CLAIMED,
        LeaseState.ACTIVE,
        LeaseState.VERIFYING,
        LeaseState.HANDOFF,
    }
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def _leases_for_path(self, path: str) -> list[ResourceLease]:
        normalized = normalize_resource_key(ResourceType.FILE, path)
        return [
            lease
            for lease in ResourceLeaseManager(self.store).list_active()
            if resources_overlap(
                ResourceType.FILE,
                normalized,
                lease.resource_type,
                lease.resource_key,
            )
        ]

    def _owner_agent(self, lease: ResourceLease) -> str:
        try:
            return self.store.get_session(lease.agent_session_id).agent_id
        except KeyError:
            return lease.agent_session_id

    @classmethod
    def _runtime_writable(cls, lease: ResourceLease, moment: datetime) -> bool:
        return (
            access_mode_can_write(lease.access_mode)
            and lease.state in cls._WRITABLE_STATES
            and not _runtime_expired(lease.expires_at, moment)
        )

    def can_write(self, agent_id: str, path: str) -> GuardResult:
        normalized = normalize_resource_key(ResourceType.FILE, path)
        resource = f"file:{normalized}"
        overlaps = self._leases_for_path(normalized)
        moment = datetime.now(timezone.utc)

        for lease in overlaps:
            owner = self._owner_agent(lease)
            if owner == agent_id and self._runtime_writable(lease, moment):
                return GuardResult(
                    decision=GuardDecision.ALLOW,
                    agent=agent_id,
                    owner=owner,
                    task_id=lease.task_id,
                    resource=resource,
                    lease_id=lease.lease_id,
                    reason="active write ownership",
                    expires_at=lease.expires_at,
                )

        for lease in overlaps:
            owner = self._owner_agent(lease)
            if owner != agent_id:
                return GuardResult(
                    decision=GuardDecision.DENY,
                    agent=agent_id,
                    owner=owner,
                    task_id=lease.task_id,
                    resource=resource,
                    lease_id=lease.lease_id,
                    reason=f"resource is owned by {owner}",
                    expires_at=lease.expires_at,
                )
            if access_mode_can_write(lease.access_mode):
                reason = (
                    "owned write lease is expired"
                    if _runtime_expired(lease.expires_at, moment)
                    else f"owned write lease is {lease.state.value}"
                )
                return GuardResult(
                    decision=GuardDecision.DENY,
                    agent=agent_id,
                    owner=owner,
                    task_id=lease.task_id,
                    resource=resource,
                    lease_id=lease.lease_id,
                    reason=reason,
                    expires_at=lease.expires_at,
                )

        return GuardResult(
            decision=GuardDecision.ALLOW_WITH_WARNING,
            agent=agent_id,
            owner=None,
            task_id=None,
            resource=resource,
            lease_id=None,
            reason="no active write lease (WRITE/EXCLUSIVE); legacy direct edit is unowned",
            expires_at=None,
        )

    def audit_paths(
        self,
        paths: list[str],
        *,
        expected_session_id: str | None = None,
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        seen: set[str] = set()
        moment = datetime.now(timezone.utc)
        for path in paths:
            normalized = normalize_resource_key(ResourceType.FILE, path)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            writable = [
                lease
                for lease in self._leases_for_path(normalized)
                if access_mode_can_write(lease.access_mode)
            ]
            current_writable = [
                lease for lease in writable if self._runtime_writable(lease, moment)
            ]

            if expected_session_id is None:
                if current_writable:
                    continue
            elif any(
                lease.agent_session_id == expected_session_id
                for lease in current_writable
            ):
                continue
            elif writable:
                owner = writable[0]
                detail = (
                    f"changed path is reserved by session {owner.agent_session_id} "
                    f"with lease state={owner.state.value}; expected {expected_session_id}"
                )
                finding = AuditFinding(
                    path=normalized,
                    event="workspace.ownership_violation",
                    detail=detail,
                    lease_id=owner.lease_id,
                    task_id=owner.task_id,
                    session_id=expected_session_id,
                )
                findings.append(finding)
                self.store.append_event(
                    WorkspaceEvent(
                        event=finding.event,
                        task_id=owner.task_id,
                        session_id=expected_session_id,
                        lease_id=owner.lease_id,
                        resource_type=ResourceType.FILE,
                        resource_key=normalized,
                        detail=detail,
                    )
                )
                continue

            detail = "changed path has no current WRITE/EXCLUSIVE lease"
            finding = AuditFinding(
                path=normalized,
                event="workspace.unowned_change",
                detail=detail,
                session_id=expected_session_id,
            )
            findings.append(finding)
            self.store.append_event(
                WorkspaceEvent(
                    event=finding.event,
                    session_id=expected_session_id,
                    resource_type=ResourceType.FILE,
                    resource_key=normalized,
                    detail=detail,
                )
            )
        return findings

    def git_changed_paths(self, repo_root: str | Path) -> list[str]:
        root = Path(repo_root).resolve()
        tracked = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        return sorted({
            normalize_resource_key(ResourceType.FILE, value)
            for value in [*tracked, *untracked]
            if value.strip()
        })
