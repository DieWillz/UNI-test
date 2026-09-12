from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from uni.devcoord.workspace_models import (
    AgentSession,
    LeaseState,
    ResourceLease,
    SessionState,
    WorkspaceEvent,
)
from uni.devcoord.workspace_store import WorkspaceStore


class AgentSessionManager:
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
