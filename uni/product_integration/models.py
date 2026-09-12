from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class LifecycleKind(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    PLAN_AVAILABLE = "plan_available"
    PROGRESS = "progress"
    REPLAN = "replan"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    STOPPED = "stopped"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ProductCommand:
    text: str
    source: str
    conversation_id: str = ""
    user_id: str = ""
    message_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: f"cmd_{uuid4().hex[:12]}")

@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    command_id: str
    kind: LifecycleKind
    text: str
    terminal: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutputDelivery:
    channel: str
    delivered: bool
    error: str = ""
