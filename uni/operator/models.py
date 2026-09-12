from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PermissionLevel(str, Enum):
    READ = "read"
    LOCAL_REVERSIBLE = "local_reversible"
    EXTERNAL_EFFECT = "external_effect"
    CRITICAL = "critical"


class ElementSource(str, Enum):
    DOM = "dom"
    UIA = "uia"
    OCR = "ocr"
    VISION = "vision"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    model_config = ConfigDict(frozen=True)


class UIElement(BaseModel):
    ref: str = Field(min_length=1)
    source: ElementSource | str
    role: str = ""
    name: str = ""
    text: str = ""
    bbox: BoundingBox | None = None
    enabled: bool = True
    value: Any = None
    checked: bool | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class WindowInfo(BaseModel):
    ref: str = ""
    title: str = ""
    executable: str = ""
    class_name: str = ""
    hwnd: int | None = None
    pid: int | None = None
    active: bool = False


class BrowserInfo(BaseModel):
    tab_id: str = ""
    url: str = ""
    title: str = ""


class SceneSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: f"scene-{uuid4().hex}")
    timestamp: str = Field(default_factory=_now)
    active_window: dict[str, Any] = Field(default_factory=dict)
    windows: list[dict[str, Any]] = Field(default_factory=list)
    browser: dict[str, Any] = Field(default_factory=dict)
    elements: list[UIElement] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TargetSpec(BaseModel):
    ref: str = ""
    source: ElementSource | str | None = None
    role: str = ""
    name: str = ""
    text: str = ""
    exact: bool = False

    @model_validator(mode="after")
    def require_identity(self) -> "TargetSpec":
        if not any((self.ref.strip(), self.name.strip(), self.text.strip())):
            raise ValueError("target requires ref, name or text")
        return self


class Postcondition(BaseModel):
    kind: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class PlanStep(BaseModel):
    id: str = Field(min_length=1)
    action: str = Field(min_length=3)
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    target: TargetSpec | None = None
    postcondition: Postcondition | None = None
    retry_budget: int = Field(default=1, ge=0, le=5)
    dependencies: list[str] = Field(default_factory=list)


class MissionPlan(BaseModel):
    goal: str = Field(min_length=1)
    steps: list[PlanStep] = Field(default_factory=list, max_length=40)
    version: int = 1

    @model_validator(mode="after")
    def validate_graph(self) -> "MissionPlan":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        known = set(ids)
        for step in self.steps:
            if step.id in step.dependencies:
                raise ValueError("step cannot depend on itself")
            missing = set(step.dependencies) - known
            if missing:
                raise ValueError(f"unknown dependencies: {sorted(missing)}")
        return self
