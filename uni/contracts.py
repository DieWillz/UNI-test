"""UNI canonical runtime contracts — ADR-0004 / CORE-002.

Every action attempted by UNI returns an ActionResult. Observations are bounded
snippets captured from the environment. AgentContext is the single serializable
goal state passed through the event loop.

Legacy ToolResult is kept for backward compatibility during migration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Legacy — kept for backward compat during migration
# ---------------------------------------------------------------------------

class ToolResult(BaseModel):
    """Returned by Capability.execute. Superseded by ActionResult."""
    success: bool
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None


class VerificationStatus(str, Enum):
    """Terminal verification states for user-visible work."""

    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"


class TaskStatus(str, Enum):
    """Canonical user-visible task states.

    ``success`` is intentionally absent. A task is complete only when it is
    ``verified``; otherwise it must remain ``not_verified`` or fail explicitly.
    """

    RUNNING = "running"
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


class Evidence(BaseModel):
    """A concrete observation used to verify an action outcome."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    data: Optional[Any] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(frozen=True)


class Verification(BaseModel):
    """Independent verification decision.

    A verified decision without evidence is structurally invalid. This is the
    central fail-closed invariant of UNI.
    """

    status: VerificationStatus = VerificationStatus.NOT_VERIFIED
    method: str = ""
    reason: str = "verification was not performed"
    evidence: list[Evidence] = Field(default_factory=list)
    verifier: str = "uni.verification_gate"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def require_evidence_for_verified(self) -> "Verification":
        if self.status is VerificationStatus.VERIFIED:
            if not self.method.strip():
                raise ValueError("verified requires a verification method")
            if not self.evidence:
                raise ValueError("verified requires at least one evidence item")
        return self


class TaskOutcome(BaseModel):
    """Canonical terminal result returned to user-facing interfaces."""

    command: str = Field(min_length=1)
    status: TaskStatus
    message: str = ""
    actions: list["ActionResult"] = Field(default_factory=list)
    observations: list["Observation"] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)
    task_id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def enforce_verified_terminal_state(self) -> "TaskOutcome":
        is_verified = self.verification.status is VerificationStatus.VERIFIED
        if self.status is TaskStatus.VERIFIED and not is_verified:
            raise ValueError("task cannot be verified without verified evidence")
        if is_verified and self.status is not TaskStatus.VERIFIED:
            raise ValueError("verified evidence requires task status=verified")
        return self

    @classmethod
    def finalize(
        cls,
        *,
        command: str,
        message: str,
        actions: list["ActionResult"] | None = None,
        observations: list["Observation"] | None = None,
        verification: Verification | None = None,
        failure_status: TaskStatus | None = None,
    ) -> "TaskOutcome":
        action_list = list(actions or [])
        observation_list = list(observations or [])
        decision = verification or Verification()
        if failure_status is not None:
            status = failure_status
        elif any(not action.success for action in action_list):
            status = TaskStatus.FAILED
        elif decision.status is VerificationStatus.VERIFIED:
            status = TaskStatus.VERIFIED
        else:
            status = TaskStatus.NOT_VERIFIED
        return cls(
            command=command,
            status=status,
            message=message,
            actions=action_list,
            observations=observation_list,
            verification=decision,
        )

    @property
    def is_success(self) -> bool:
        return self.status is TaskStatus.VERIFIED


# ---------------------------------------------------------------------------
# Canonical contracts (ADR-0004)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Action(BaseModel):
    """A single canonical action descriptor.

    The canonical name uses dotted ``capability.action`` form
    (e.g. ``browser.navigate``, ``xtoys.set_intensity``).
    """
    name: str = Field(description="Canonical capability.action name")
    params: dict[str, Any] = Field(default_factory=dict)
    id: str = Field(
        default_factory=lambda: str(uuid4())[:8],
        description="Unique action id for task tracking",
    )

    model_config = ConfigDict(frozen=True)


class ActionResult(BaseModel):
    """Result of a single action execution.

    Distinguished from the legacy ToolResult: carries verification status,
    retry count, and an explicit Action reference.
    """
    action: Action
    success: bool
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None
    verified: bool = Field(
        default=False,
        description="True only when the outcome was independently observed",
    )
    retry_count: int = Field(default=0, ge=0)
    timestamp: str = Field(default_factory=_utc_now)

    @classmethod
    def from_tool_result(
        cls,
        tool_result: ToolResult,
        action_name: str,
        action_params: dict[str, Any] | None = None,
        *,
        verified: bool = False,
        retry_count: int = 0,
    ) -> "ActionResult":
        """Upgrade a legacy ToolResult to an ActionResult."""
        return cls(
            action=Action(name=action_name, params=action_params or {}),
            success=tool_result.success,
            message=tool_result.message,
            data=tool_result.data,
            error=tool_result.error,
            verified=verified,
            retry_count=retry_count,
        )

    def to_tool_result(self) -> ToolResult:
        """Downgrade to a legacy ToolResult."""
        return ToolResult(
            success=self.success,
            message=self.message,
            data=self.data,
            error=self.error,
        )


class Observation(BaseModel):
    """A bounded environmental observation.

    Captured from Vision, Camera, Browser tab content, or screen watch.
    Observations are snapshots, not permanent facts.
    """
    source: str = Field(description="Capability or event that produced this observation")
    summary: str = Field(default="", description="Human-readable summary")
    data: Optional[Any] = Field(default=None, description="Raw observation payload")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=_utc_now)

    model_config = ConfigDict(frozen=True)


class AgentContext(BaseModel):
    """Single serializable mutable goal state.

    Passed through the event loop; injected into Agent and EventLoop.
    Planner, Router, and Verifier read from and write to this context.
    """
    goal: str = Field(default="", description="Current user goal")
    state: str = Field(default="idle", description="Agent state label")
    action_history: list[ActionResult] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    retry_budget: int = Field(default=3, ge=0, le=10)
    replan_count: int = Field(default=0, ge=0)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)

    def record_action(self, result: ActionResult) -> None:
        self.action_history.append(result)

    def record_observation(self, obs: Observation) -> None:
        self.observations.append(obs)
        # Keep bounded
        if len(self.observations) > 200:
            self.observations = self.observations[-100:]

    def last_result(self) -> ActionResult | None:
        return self.action_history[-1] if self.action_history else None

    def last_error(self) -> str | None:
        last = self.last_result()
        return last.error if last and not last.success else None

    def remaining_retries(self) -> int:
        return max(0, self.retry_budget - self.replan_count)
