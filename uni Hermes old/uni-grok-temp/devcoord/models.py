from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"


class ArtifactRef(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    media_type: str = "application/octet-stream"
    text_excerpt: str | None = Field(default=None, max_length=50_000)


class ProviderResult(BaseModel):
    provider_id: str = Field(min_length=1, max_length=100)
    transport: Literal["api", "browser"]
    content: str = Field(max_length=200_000)
    created_at: str = Field(default_factory=utc_now)
    error: str | None = Field(default=None, max_length=4000)


class HandoffPackage(BaseModel):
    task_id: str
    goal: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=20_000)
    from_agent: str = Field(default="coordinator", max_length=100)
    to_agent: str = Field(min_length=1, max_length=100)
    context_summary: str = Field(default="", max_length=20_000)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    artifacts: list[ArtifactRef] = Field(default_factory=list, max_length=50)
    previous_results: list[ProviderResult] = Field(default_factory=list, max_length=20)
    expected_output: str = Field(default="Structured review and recommendations", max_length=4000)


class DevelopmentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=300)
    goal: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=20_000)
    context_summary: str = Field(default="", max_length=20_000)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    expected_output: str = Field(default="Structured review and recommendations", max_length=4000)
    provider_sequence: list[str] = Field(default_factory=list, max_length=10)
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    requested_provider_count: int = Field(default=1, ge=1, le=10)
    continue_on_error: bool = False
    artifact_paths: list[str] = Field(default_factory=list, max_length=50)
    status: TaskStatus = TaskStatus.PENDING
    next_provider_index: int = Field(default=0, ge=0)
    results: list[ProviderResult] = Field(default_factory=list, max_length=20)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_cursor(self) -> "DevelopmentTask":
        if self.next_provider_index > len(self.provider_sequence):
            raise ValueError("next_provider_index exceeds provider_sequence")
        if len(set(self.provider_sequence)) != len(self.provider_sequence):
            raise ValueError("provider_sequence contains duplicates")
        if not self.provider_sequence and not self.required_capabilities:
            raise ValueError("provider_sequence or required_capabilities is required")
        return self


class ProviderConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,99}$")
    display_name: str = Field(min_length=1, max_length=200)
    transport: Literal["api", "browser"]
    enabled: bool = False
    capabilities: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=10_000)
    timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
    max_response_chars: int = Field(default=50_000, ge=1000, le=200_000)
    api_cost: Literal["free", "paid", "unknown"] = "unknown"
    base_url: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    browser_url: str | None = None
    browser_profile_dir: str | None = None
    prompt_selector: str | None = None
    submit_selector: str | None = None
    response_selector: str | None = None

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "ProviderConfig":
        if self.transport == "api" and (not self.base_url or not self.model):
            raise ValueError("api provider requires base_url and model")
        if self.transport == "browser":
            required = (self.browser_url, self.browser_profile_dir, self.prompt_selector, self.response_selector)
            if not all(required):
                raise ValueError(
                    "browser provider requires browser_url, browser_profile_dir, "
                    "prompt_selector, and response_selector"
                )
        return self


class CoordinatorEvent(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    event: str = Field(min_length=1, max_length=100)
    task_id: str
    provider_id: str | None = None
    detail: str = Field(default="", max_length=4000)
