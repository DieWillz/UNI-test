from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from uni.devcoord.workspace_models import (
    AgentSession,
    LeaseState,
    ResourceLease,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


class AgentSessionManager:
    """Lifecycle manager for MAWC executor sessions."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    @staticmethod
    def _window(ttl_seconds: float) -> tuple[str, str]:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = datetime.now(timezone.utc)
        return now.isoformat(), (now + timedelta(seconds=ttl_seconds)).isoformat()
    def register(
        self,
        *,
        agent_id: str,
        display_name: str,
        task_id: str | None = None,
        session_id: str | None = None,
        process_id: int | None = None,
        worktree_path: str | None = None,
        capabilities: list[str] | None = None,
        ttl_seconds: float = 600.0,
    ) -> AgentSession:
        heartbeat_at, expires_at = self._window(ttl_seconds)
        session = AgentSession(
            session_id=session_id or str(uuid4()),
            agent_id=agent_id,
            display_name=display_name,
            task_id=task_id,
            process_id=process_id,
            worktree_path=worktree_path,
            capabilities=list(capabilities or []),
            state=SessionState.ACTIVE,
            heartbeat_at=heartbeat_at,
            expires_at=expires_at,
        )
        with self.store.transaction(immediate=True) as conn:
            self.store.save_session(session, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="session.registered",
                    task_id=task_id,
                    session_id=session.session_id,
                ),
                conn=conn,
            )
        return session

    def get(self, session_id: str) -> AgentSession:
        return self.store.get_session(session_id)

    def heartbeat(self, session_id: str, *, ttl_seconds: float = 600.0) -> AgentSession:
        heartbeat_at, expires_at = self._window(ttl_seconds)
        with self.store.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown agent session: {session_id}")
            session = AgentSession.model_validate(json.loads(row[0]))
            if session.state is SessionState.STALE:
                raise RuntimeError("stale session requires controlled takeover")
            if session.state is SessionState.STOPPED:
                raise RuntimeError("stopped session requires explicit resume")
            next_state = (
                SessionState.VERIFYING
                if session.state is SessionState.VERIFYING
                else SessionState.ACTIVE
            )
            refreshed = session.model_copy(
                update={
                    "state": next_state,
                    "heartbeat_at": heartbeat_at,
                    "expires_at": expires_at,
                }
            )
            self.store.save_session(refreshed, conn=conn)
            rows = conn.execute(
                "SELECT payload_json FROM resource_leases "
                "WHERE agent_session_id=? AND state!=?",
                (session_id, LeaseState.RELEASED.value),
            ).fetchall()
            for lease_row in rows:
                lease = ResourceLease.model_validate(json.loads(lease_row[0])).model_copy(
                    update={"heartbeat_at": heartbeat_at, "expires_at": expires_at}
                )
                self.store.save_resource_lease(lease, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="session.heartbeat",
                    task_id=refreshed.task_id,
                    session_id=session_id,
                ),
                conn=conn,
            )
        return refreshed

    def mark_stale(self, *, now: datetime | None = None) -> list[AgentSession]:
        moment = now or datetime.now(timezone.utc)
        stale_sessions: list[AgentSession] = []
        with self.store.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT session_id, payload_json FROM agent_sessions WHERE state NOT IN (?, ?)",
                (SessionState.STALE.value, SessionState.STOPPED.value),
            ).fetchall()
            for session_id, payload_json in rows:
                session = AgentSession.model_validate(json.loads(payload_json))
                if not session.expires_at or datetime.fromisoformat(session.expires_at) > moment:
                    continue
                stale = session.model_copy(update={"state": SessionState.STALE})
                stale_sessions.append(stale)
                self.store.save_session(stale, conn=conn)
                lease_rows = conn.execute(
                    "SELECT payload_json FROM resource_leases "
                    "WHERE agent_session_id=? AND state!=?",
                    (session_id, LeaseState.RELEASED.value),
                ).fetchall()
                for lease_row in lease_rows:
                    lease = ResourceLease.model_validate(json.loads(lease_row[0])).model_copy(
                        update={"state": LeaseState.STALE}
                    )
                    self.store.save_resource_lease(lease, conn=conn)
                self.store.append_event(
                    WorkspaceEvent(
                        event="session.stale",
                        task_id=stale.task_id,
                        session_id=stale.session_id,
                    ),
                    conn=conn,
                )
        return stale_sessions

    def attach_process(
        self,
        session_id: str,
        *,
        process_id: int,
        stdout_log_path: str,
        stderr_log_path: str,
    ) -> AgentSession:
        session = self.store.get_session(session_id)
        if session.state is SessionState.STALE:
            raise RuntimeError("stale session requires controlled takeover")
        attached = session.model_copy(
            update={
                "process_id": process_id,
                "stdout_log_path": stdout_log_path,
                "stderr_log_path": stderr_log_path,
                "state": SessionState.ACTIVE,
                "last_observation": f"process started pid={process_id}",
            }
        )
        with self.store.transaction(immediate=True) as conn:
            self.store.save_session(attached, conn=conn)
            self._set_lease_state(session_id, LeaseState.ACTIVE, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="session.process_attached",
                    task_id=attached.task_id,
                    session_id=session_id,
                    detail=f"pid={process_id}",
                ),
                conn=conn,
            )
        return attached

    def begin_verification(
        self,
        session_id: str,
        *,
        observation: str = "",
    ) -> AgentSession:
        session = self.store.get_session(session_id)
        verifying = session.model_copy(
            update={
                "state": SessionState.VERIFYING,
                "last_observation": observation[:4000],
            }
        )
        with self.store.transaction(immediate=True) as conn:
            self.store.save_session(verifying, conn=conn)
            self._set_lease_state(session_id, LeaseState.VERIFYING, conn=conn)
            self.store.append_event(
                WorkspaceEvent(
                    event="session.verifying",
                    task_id=verifying.task_id,
                    session_id=session_id,
                    detail=observation[:4000],
                ),
                conn=conn,
            )
        return verifying

    def _set_lease_state(self, session_id: str, state: LeaseState, *, conn=None) -> None:
        if conn is None:
            with self.store.transaction(immediate=True) as transaction:
                self._set_lease_state(session_id, state, conn=transaction)
            return
        rows = conn.execute(
            "SELECT payload_json FROM resource_leases "
            "WHERE agent_session_id=? AND state!=?",
            (session_id, LeaseState.RELEASED.value),
        ).fetchall()
        for row in rows:
            lease = ResourceLease.model_validate(json.loads(row[0])).model_copy(
                update={"state": state}
            )
            self.store.save_resource_lease(lease, conn=conn)
