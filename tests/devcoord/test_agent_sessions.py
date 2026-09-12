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


def test_register_rolls_back_session_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_register_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='session.registered' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        sessions.register(
            agent_id="hermes",
            display_name="Hermes",
            task_id="UNI-141",
            session_id="session-register-fails",
        )

    assert store.list_sessions() == []


def test_heartbeat_rolls_back_session_and_lease_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    registered = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        session_id="session-hermes",
        ttl_seconds=1,
    )
    lease = ResourceLeaseManager(store).claim(
        "UNI-142",
        registered.session_id,
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="telegram-runtime")],
        ttl_seconds=1,
    )[0]
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_heartbeat_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='session.heartbeat' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        sessions.heartbeat(registered.session_id, ttl_seconds=600)

    after_session = sessions.get(registered.session_id)
    after_lease = ResourceLeaseManager(store).list_active()[0]
    assert after_session.heartbeat_at == registered.heartbeat_at
    assert after_session.expires_at == registered.expires_at
    assert after_lease.heartbeat_at == lease.heartbeat_at
    assert after_lease.expires_at == lease.expires_at


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


def test_mark_stale_rolls_back_state_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    session = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-142",
        session_id="session-hermes",
        ttl_seconds=600,
    )
    store.save_session(session.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"}))
    lease = ResourceLeaseManager(store).claim(
        "UNI-142",
        session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )[0]
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_stale_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='session.stale' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        sessions.mark_stale(now=datetime(2026, 9, 10, tzinfo=timezone.utc))

    assert sessions.get(session.session_id).state is SessionState.ACTIVE
    assert ResourceLeaseManager(store).list_active()[0].state is lease.state


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


def test_controlled_takeover_rolls_back_state_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    session = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-143",
        session_id="session-takeover-fails",
        ttl_seconds=600,
    )
    lease = ResourceLeaseManager(store).claim(
        "UNI-143",
        session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )[0]
    store.save_session(session.model_copy(update={"state": SessionState.STALE}))
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_takeover_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='takeover.prepared' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        ControlledTakeover(store).prepare(
            session.session_id,
            "C:/LLM/UNI/.uni-dev/checkpoints/UNI-143/hermes.json",
        )

    assert sessions.get(session.session_id).state is SessionState.STALE
    assert ResourceLeaseManager(store).list_active()[0].state is lease.state


def test_attach_process_rolls_back_session_and_lease_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    session = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-144",
        session_id="session-hermes-attach",
        ttl_seconds=600,
    )
    lease = ResourceLeaseManager(store).claim(
        "UNI-144",
        session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/agent.py")],
        ttl_seconds=600,
    )[0]
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_attach_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='session.process_attached' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        sessions.attach_process(
            session.session_id,
            process_id=12345,
            stdout_log_path="stdout.log",
            stderr_log_path="stderr.log",
        )

    after_session = sessions.get(session.session_id)
    after_lease = ResourceLeaseManager(store).list_active()[0]
    assert after_session.process_id is None
    assert after_session.state is session.state
    assert after_lease.state is lease.state


def test_begin_verification_rolls_back_session_and_lease_when_event_write_fails(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    session = sessions.register(
        agent_id="hermes",
        display_name="Hermes",
        task_id="UNI-145",
        session_id="session-hermes-verify",
        ttl_seconds=600,
    )
    lease = ResourceLeaseManager(store).claim(
        "UNI-145",
        session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )[0]
    with store.transaction(immediate=True) as conn:
        conn.execute(
            "CREATE TRIGGER fail_verifying_event BEFORE INSERT ON workspace_events "
            "WHEN NEW.event='session.verifying' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )

    with pytest.raises(Exception, match="boom"):
        sessions.begin_verification(session.session_id, observation="done")

    after_session = sessions.get(session.session_id)
    after_lease = ResourceLeaseManager(store).list_active()[0]
    assert after_session.state is session.state
    assert after_session.last_observation == session.last_observation
    assert after_lease.state is lease.state


def test_stopped_session_heartbeat_does_not_resume_agent(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    sessions = AgentSessionManager(store)
    stopped = sessions.register(
        agent_id="hermes", display_name="Hermes", session_id="stopped", ttl_seconds=600
    )
    store.save_session(stopped.model_copy(update={"state": SessionState.STOPPED}))

    with pytest.raises(RuntimeError, match="stopped|resume"):
        sessions.heartbeat("stopped", ttl_seconds=600)

    assert store.get_session("stopped").state is SessionState.STOPPED
