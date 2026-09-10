from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from uni.devcoord.workspace_models import AgentSession, WorkspaceEvent, WorkspaceTask


class WorkspaceStore:
    VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    task_id TEXT,
                    state TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO workspace_meta(key, value) VALUES('version', ?)",
                (str(self.VERSION),),
            )
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_tasks (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    assigned_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_tasks_state_priority
                    ON workspace_tasks(state, priority DESC, created_at, task_id);
                CREATE TABLE IF NOT EXISTS resource_leases (
                    lease_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_session_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_key TEXT NOT NULL,
                    access_mode TEXT NOT NULL,
                    state TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(agent_session_id) REFERENCES agent_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_resource_leases_active
                    ON resource_leases(resource_type, resource_key, access_mode, state);
                CREATE INDEX IF NOT EXISTS idx_resource_leases_session
                    ON resource_leases(agent_session_id, state);
                CREATE TABLE IF NOT EXISTS workspace_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event TEXT NOT NULL,
                    task_id TEXT,
                    session_id TEXT,
                    lease_id TEXT,
                    resource_type TEXT,
                    resource_key TEXT,
                    detail TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def journal_mode(self) -> str:
        with self._connect() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def foreign_keys_enabled(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
        return bool(row[0])

    def save_workspace_task(self, task: WorkspaceTask) -> None:
        payload = task.model_dump_json()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO workspace_tasks(
                    task_id, state, priority, assigned_session_id,
                    created_at, updated_at, payload_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    state=excluded.state,
                    priority=excluded.priority,
                    assigned_session_id=excluded.assigned_session_id,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json
                """,
                (
                    task.id,
                    task.state.value,
                    task.priority,
                    task.assigned_session_id,
                    task.created_at,
                    task.updated_at,
                    payload,
                ),
            )

    def get_workspace_task(self, task_id: str) -> WorkspaceTask:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM workspace_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown workspace task: {task_id}")
        return WorkspaceTask.model_validate(json.loads(row[0]))

    def list_workspace_tasks(self) -> list[WorkspaceTask]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM workspace_tasks ORDER BY rowid"
            ).fetchall()
        return [WorkspaceTask.model_validate(json.loads(row[0])) for row in rows]

    def save_session(self, session: AgentSession) -> None:
        payload = session.model_dump_json()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions(
                    session_id, agent_id, task_id, state,
                    heartbeat_at, expires_at, payload_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    agent_id=excluded.agent_id,
                    task_id=excluded.task_id,
                    state=excluded.state,
                    heartbeat_at=excluded.heartbeat_at,
                    expires_at=excluded.expires_at,
                    payload_json=excluded.payload_json
                """,
                (
                    session.session_id,
                    session.agent_id,
                    session.task_id,
                    session.state.value,
                    session.heartbeat_at,
                    session.expires_at,
                    payload,
                ),
            )

    def get_session(self, session_id: str) -> AgentSession:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown agent session: {session_id}")
        return AgentSession.model_validate(json.loads(row[0]))

    def list_sessions(self) -> list[AgentSession]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM agent_sessions ORDER BY rowid"
            ).fetchall()
        return [AgentSession.model_validate(json.loads(row[0])) for row in rows]

    def append_event(self, event: WorkspaceEvent) -> None:
        payload = event.model_dump_json()
        with self.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO workspace_events(
                    event_id, timestamp, event, task_id, session_id, lease_id,
                    resource_type, resource_key, detail, payload_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.event,
                    event.task_id,
                    event.session_id,
                    event.lease_id,
                    event.resource_type.value if event.resource_type else None,
                    event.resource_key,
                    event.detail,
                    payload,
                ),
            )

    def list_events(self, *, limit: int = 100) -> list[WorkspaceEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM workspace_events
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ?
                """,
                (max(0, limit),),
            ).fetchall()
        return [WorkspaceEvent.model_validate(json.loads(row[0])) for row in rows]
