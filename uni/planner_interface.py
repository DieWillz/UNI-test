"""
Planner Interface for UNI Agent
Author: DeepSeek (Algorithms Engineer)
Date: 2026-07-30
Target: Build 12 — Planner Integration

CONTRACT — менять только через DECISION координатора.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
import time


# ═══════════════════════════════════════════════════
# 1. Data Structures
# ═══════════════════════════════════════════════════

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorType(str, Enum):
    TRANSIENT = "transient"    # can retry
    PERMANENT = "permanent"    # do not retry
    TIMEOUT = "timeout"        # can retry with longer timeout


@dataclass
class Action:
    """Atomic action for a capability."""
    name: str                   # e.g. "browser.click", "speech.say"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of executing an Action."""
    action: Action
    status: str                 # "success" | "failure" | "timeout"
    data: Any = None
    error: Optional[str] = None
    error_type: ErrorType = ErrorType.TRANSIENT
    timestamp: float = field(default_factory=time.time)


@dataclass
class Task:
    """One task in the queue."""
    id: str
    action: Action
    priority: int = 1          # 0 = critical, 1 = normal, 2 = background
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0
    status: TaskStatus = TaskStatus.PENDING


# ═══════════════════════════════════════════════════
# 2. Planner Interface
# ═══════════════════════════════════════════════════

class Planner:
    """
    Goal → TaskTree decomposition.

    LLM is called ONCE per plan() or replan().
    All other decisions are deterministic rules.
    """

    def __init__(self, llm_client, capability_registry, config: dict):
        """
        Args:
            llm_client: Brain-like object with `async chat(prompt, system) → str`.
            capability_registry: Object with `describe_all() → list[dict]`.
            config: Algorithm parameters (base_delay, max_replans, etc.).
        """
        self._llm = llm_client
        self._registry = capability_registry
        self._cfg = config

    async def plan(self, goal: str, context: list[ActionResult]) -> list[Task]:
        """
        Decompose a user goal into a sequence of Tasks.

        Steps (deterministic after LLM call):
        1. Build prompt with capability descriptions + context.
        2. LLM returns JSON plan.
        3. Validate actions exist in registry.
        4. Set retry limits, priorities, dependencies.

        Returns:
            Ordered list of Task objects (ready for TaskQueue).
        """
        ...

    async def replan(
        self, goal: str, failed_task: Task, history: list[ActionResult]
    ) -> list[Task]:
        """
        Re-plan after a failure. Same as plan() but with failure context.
        Called when retries exhausted AND max_replans not yet reached.
        """
        ...


# ═══════════════════════════════════════════════════
# 3. Task Queue Interface
# ═══════════════════════════════════════════════════

class TaskQueue:
    """Priority queue with dependency resolution."""

    def __init__(self):
        self._tasks: list[Task] = []
        self._completed: set[str] = set()

    async def push(self, task: Task) -> None:
        """Insert task, maintain priority order."""
        ...

    async def pop(self) -> Optional[Task]:
        """Return highest-priority ready task (all deps completed)."""
        ...

    async def mark_completed(self, task_id: str) -> None:
        """Mark task as successfully done."""
        ...

    async def requeue(self, task: Task, increment_retry: bool = True) -> None:
        """Put task back (for retry)."""
        ...

    async def clear_pending(self) -> None:
        """Remove all non-running tasks (for re-plan)."""
        ...

    def is_empty(self) -> bool:
        """True if no tasks left."""
        ...


# ═══════════════════════════════════════════════════
# 4. Retry / Recovery Logic
# ═══════════════════════════════════════════════════

def classify_error(error: str) -> ErrorType:
    """
    Deterministic error classification.
    TRANSIENT: element_not_found, timeout, network_error, context_lost
    PERMANENT: invalid_selector, permission_denied, capability_unavailable
    """
    ...


def retry_delay(retry_count: int, base: float = 0.5, max_delay: float = 8.0) -> float:
    """
    Exponential backoff with jitter.
    delay = min(base * 2^retry_count, max_delay) * random(0.8, 1.2)
    """
    ...


# ═══════════════════════════════════════════════════
# 5. Priority & Retry Defaults (from config)
# ═══════════════════════════════════════════════════

DEFAULT_PRIORITY_MAP = {
    "browser.launch": 0,
    "computer.click": 0,
    "computer.type": 0,
    "computer.press": 0,
    "browser.goto": 1,
    "browser.wait_for_selector": 1,
}

DEFAULT_RETRY_OVERRIDES = {
    "browser.goto": 1,
    "browser.wait_for_selector": 5,
    "computer.click": 3,
    "computer.type": 2,
}