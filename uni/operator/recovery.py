from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureKind(str, Enum):
    TARGET_STALE = "TARGET_STALE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    WINDOW_CHANGED = "WINDOW_CHANGED"
    BROWSER_DISCONNECTED = "BROWSER_DISCONNECTED"
    ACTION_FAILED = "ACTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    STOP_REQUESTED = "STOP_REQUESTED"


class RecoveryStrategy(str, Enum):
    REOBSERVE = "reobserve"
    REPLAN = "replan"
    BLOCKED = "blocked"
    STOP = "stop"


@dataclass(frozen=True)
class RecoveryDecision:
    strategy: RecoveryStrategy
    reason: str


class RecoveryEngine:
    """Classify at provider boundaries; never replay an uncertain side effect."""

    def __init__(self, *, max_replans: int = 2) -> None:
        self.max_replans = max(0, min(int(max_replans), 5))

    @staticmethod
    def classify(error: str) -> FailureKind:
        low = (error or "").casefold()
        groups = (
            (FailureKind.STOP_REQUESTED, ("stop_requested", "inputstopped", "physical_input_stopped")),
            (FailureKind.AMBIGUOUS_TARGET, ("ambiguous", "targetambiguous")),
            (FailureKind.BROWSER_DISCONNECTED, ("cdp_attach", "browser_disconnected", "connection closed", "targetclosed")),
            (FailureKind.TARGET_STALE, ("stale_ref", "target_stale", "snapshot_id_required")),
            (FailureKind.WINDOW_CHANGED, ("window_changed", "window_missing", "window not found")),
            (FailureKind.TARGET_NOT_FOUND, ("target_not_found", "targetnotfound", "element_not_found")),
            (FailureKind.VERIFICATION_FAILED, ("verification", "postcondition", "observation")),
        )
        for kind, markers in groups:
            if any(marker in low for marker in markers):
                return kind
        return FailureKind.ACTION_FAILED

    def decide(self, *, error: str, attempt: int, replan_count: int,
               effect_may_have_occurred: bool = False) -> RecoveryDecision:
        kind = self.classify(error)
        if kind is FailureKind.STOP_REQUESTED:
            return RecoveryDecision(RecoveryStrategy.STOP, kind.value)
        if effect_may_have_occurred:
            return RecoveryDecision(RecoveryStrategy.BLOCKED, "effect_outcome_uncertain")
        if kind in {FailureKind.ACTION_FAILED, FailureKind.VERIFICATION_FAILED}:
            return RecoveryDecision(RecoveryStrategy.BLOCKED, kind.value)
        if attempt == 0 and kind in {FailureKind.TARGET_STALE, FailureKind.TARGET_NOT_FOUND}:
            return RecoveryDecision(RecoveryStrategy.REOBSERVE, kind.value)
        if replan_count < self.max_replans:
            return RecoveryDecision(RecoveryStrategy.REPLAN, kind.value)
        return RecoveryDecision(RecoveryStrategy.BLOCKED, "replan_budget_exhausted")
