from __future__ import annotations

from uni.operator.recovery import RecoveryEngine


def test_stale_ref_reobserves_before_replanning() -> None:
    engine = RecoveryEngine(max_replans=2)
    first = engine.decide(error="stale_ref", attempt=0, replan_count=0)
    second = engine.decide(error="stale_ref", attempt=1, replan_count=0)
    assert first.strategy == "reobserve"
    assert second.strategy == "replan"


def test_missing_window_uses_focus_then_launch_then_replan() -> None:
    engine = RecoveryEngine(max_replans=2)
    strategies = [
        engine.decide(error="window_missing", attempt=i, replan_count=0).strategy
        for i in range(3)
    ]
    assert strategies == ["focus_window", "launch_app", "replan"]


def test_replan_budget_ends_fail_closed() -> None:
    engine = RecoveryEngine(max_replans=1)
    decision = engine.decide(error="unknown", attempt=3, replan_count=1)
    assert decision.strategy == "blocked"
