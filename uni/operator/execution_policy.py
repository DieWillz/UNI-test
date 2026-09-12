from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
from math import isfinite

from .models import SceneSnapshot, UIElement


class ExecutionMode(str, Enum):
    VISIBLE = "visible"
    BALANCED_VISIBLE = "balanced_visible"
    FAST = "fast"


class ExecutionMethod(str, Enum):
    DIRECT = "direct"
    VISIBLE = "visible"


@dataclass(frozen=True)
class ExecutionDecision:
    method: ExecutionMethod
    mode: ExecutionMode
    reason: str


class ExecutionPolicy:
    """Deterministic execution method selection. LLM does NOT choose the method.

    Rules:
    Visible methods require a fresh, enabled UIA target in the foreground window.
    DOM geometry is never assumed to be screen-space geometry.
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.BALANCED_VISIBLE) -> None:
        self.mode = mode

    def decide(self, action_name: str, target: UIElement | None = None, *,
               scene: SceneSnapshot | None = None, visible_available: bool = False) -> ExecutionDecision:
        safe = False
        if target is not None and scene is not None and target.bbox is not None:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(scene.timestamp)).total_seconds()
                box = target.bbox
                safe = (0 <= age <= 2 and target.enabled and target.confidence >= 0.9
                        and target.source == "uia" and bool(scene.active_window.get("hwnd"))
                        and not scene.errors and not target.metadata.get("sensitive")
                        and all(isfinite(v) for v in (box.x, box.y, box.width, box.height)))
            except (ValueError, TypeError):
                safe = False
        visible = (self.mode is not ExecutionMode.FAST and visible_available and safe
                   and self._is_physical(action_name))
        return ExecutionDecision(ExecutionMethod.VISIBLE if visible else ExecutionMethod.DIRECT,
            self.mode, "fresh UIA target: visible input" if visible else "structural execution required")

    @staticmethod
    def _is_physical(action_name: str) -> bool:
        physical_actions = {
            "operator.desktop.click", "operator.desktop.fill", "operator.desktop.press",
            "operator.desktop.focus", "operator.desktop.press_system_key",
            "operator.desktop.check", "operator.desktop.uncheck",
        }
        return action_name in physical_actions
