from __future__ import annotations

from uni.operator.execution_policy import ExecutionMethod, ExecutionMode, ExecutionPolicy


def test_visible_mode_uses_visible_method_for_physical_actions() -> None:
    policy = ExecutionPolicy(mode=ExecutionMode.VISIBLE)
    decision = policy.decide("operator.desktop.click")
    assert decision.method == ExecutionMethod.VISIBLE
    assert decision.mode == ExecutionMode.VISIBLE


def test_fast_mode_uses_direct_method_for_physical_actions() -> None:
    policy = ExecutionPolicy(mode=ExecutionMode.FAST)
    decision = policy.decide("operator.desktop.click")
    assert decision.method == ExecutionMethod.DIRECT
    assert decision.mode == ExecutionMode.FAST


def test_balanced_mode_prefers_direct_for_physical() -> None:
    policy = ExecutionPolicy(mode=ExecutionMode.BALANCED_VISIBLE)
    decision = policy.decide("operator.desktop.fill")
    assert decision.method == ExecutionMethod.DIRECT
    assert decision.mode == ExecutionMode.BALANCED_VISIBLE


def test_non_physical_action_always_direct() -> None:
    policy = ExecutionPolicy(mode=ExecutionMode.VISIBLE)
    decision = policy.decide("operator.desktop.inspect")
    assert decision.method == ExecutionMethod.DIRECT
    decision = policy.decide("browser.navigate")
    assert decision.method == ExecutionMethod.DIRECT


def test_unknown_action_defaults_to_direct() -> None:
    policy = ExecutionPolicy(mode=ExecutionMode.VISIBLE)
    decision = policy.decide("operator.desktop.unknown_action")
    assert decision.method == ExecutionMethod.DIRECT
