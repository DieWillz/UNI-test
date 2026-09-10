from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from uni.devcoord.models import utc_now


class ResourceType(str, Enum):
    FILE = "file"
    TREE = "tree"
    LOGIC = "logic"
    CONTRACT = "contract"
    GLOBAL = "global"


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


class LeaseState(str, Enum):
    CLAIMED = "claimed"
    ACTIVE = "active"
    VERIFYING = "verifying"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    STALE = "stale"
    HANDOFF = "handoff"
    RELEASED = "released"


class SessionState(str, Enum):
    ACTIVE = "active"
    VERIFYING = "verifying"
    STALE = "stale"
    STOPPED = "stopped"


class ResourceRequest(BaseModel):
    resource_type: ResourceType
    resource_key: str = Field(min_length=1, max_length=1000)
    access_mode: AccessMode = AccessMode.WRITE


class ResourceLease(BaseModel):
    lease_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(min_length=1, max_length=300)
    agent_session_id: str = Field(min_length=1, max_length=300)
    resource_type: ResourceType
    resource_key: str = Field(min_length=1, max_length=1000)
    access_mode: AccessMode = AccessMode.WRITE
    state: LeaseState = LeaseState.CLAIMED
    base_hash: str | None = None
    current_hash: str | None = None
    created_at: str = Field(default_factory=utc_now)
    heartbeat_at: str = Field(default_factory=utc_now)
    expires_at: str | None = None
    released_at: str | None = None


class AgentSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    task_id: str | None = Field(default=None, max_length=300)
    process_id: int | None = Field(default=None, ge=1)
    worktree_path: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    state: SessionState = SessionState.ACTIVE
    started_at: str = Field(default_factory=utc_now)
    heartbeat_at: str = Field(default_factory=utc_now)
    expires_at: str | None = None
    last_observation: str = Field(default="", max_length=4000)


class WorkspaceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=utc_now)
    event: str = Field(min_length=1, max_length=100)
    task_id: str | None = Field(default=None, max_length=300)
    session_id: str | None = Field(default=None, max_length=300)
    lease_id: str | None = Field(default=None, max_length=300)
    resource_type: ResourceType | None = None
    resource_key: str | None = Field(default=None, max_length=1000)
    detail: str = Field(default="", max_length=4000)
