from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from uni.devcoord.leases import LeaseConflictError, ResourceLeaseManager
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.takeover import ControlledTakeover
from uni.devcoord.workspace_models import (
    LeaseState,
    ResourceRequest,
    ResourceType,
    SessionState,
)
from uni.devcoord.workspace_store import WorkspaceStore


def test_register_and_heartbeat_refresh_session_and_lease_ttl(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    registered = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        session_id="session-hermes",
        ttl_seconds=1,
    )

    leases = ResourceLeaseManager(store)
    lease = leases.claim(
        "UNI-142",
        registered.session_id,
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="telegram-runtime")],
        ttl_seconds=1,
    )[0]

    refreshed = sessions.heartbeat(registered.session_id, ttl_seconds=600)
    refreshed_lease = ResourceLeaseManager(store).list_active()[0]

    assert refreshed.state is SessionState.ACTIVE
    assert refreshed.heartbeat_at >= registered.heartbeat_at
    assert refreshed.expires_at > registered.expires_at
    assert refreshed_lease.heartbeat_at >= lease.heartbeat_at
    assert refreshed_lease.expires_at > lease.expires_at


def test_expired_session_becomes_stale_without_releasing_write_lease(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    stale_candidate = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        session_id="session-hermes",
        ttl_seconds=600,
    )
    store.save_session(
        stale_candidate.model_copy(
            update={"expires_at": "2000-01-01T00:00:00+00:00"}
        )
    )
    leases = ResourceLeaseManager(store)
    leases.claim(
        "UNI-142",
        "session-hermes",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )

    stale = sessions.mark_stale(now=datetime(2026, 9, 10, tzinfo=timezone.utc))
    active_lease = leases.list_active()[0]

    assert [item.session_id for item in stale] == ["session-hermes"]
    assert sessions.get("session-hermes").state is SessionState.STALE
    assert active_lease.state is LeaseState.STALE

    sessions.register(
        agent_id="codex",
        display_name="Codex",
        task_id="UNI-143",
        session_id="session-codex",
        ttl_seconds=600,
    )
    with pytest.raises(LeaseConflictError):
        leases.claim(
            "UNI-143",
            "session-codex",
            [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
            ttl_seconds=600,
        )


def test_controlled_takeover_requires_stale_session_and_snapshot(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    session = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        session_id="session-hermes",
        ttl_seconds=600,
    )
    store.save_session(session.model_copy(update={"state": SessionState.STALE}))
    takeover = ControlledTakeover(store)

    with pytest.raises(ValueError, match="snapshot"):
        takeover.prepare("session-hermes", "")

    record = takeover.prepare(
        "session-hermes",
        "C:/LLM/UNI/.uni-dev/checkpoints/UNI-142/hermes.json",
    )

    assert record.stale_session_id == "session-hermes"
    assert record.task_id == "UNI-142"
    assert record.snapshot_ref.endswith("hermes.json")
    assert ResourceLeaseManager(store).list_active() == []
    assert store.list_events(limit=10)[0].event == "takeover.prepared"
