"""Тесты заглушки safety: всё разрешено, whitelist автономии работает."""

from __future__ import annotations

from uni.safety import SafetyConfig, SafetyGuard


def test_validate_always_allowed():
    g = SafetyGuard(SafetyConfig())
    ok, reason = g.validate_tool("xtoys_set_intensity", {"value": 100})
    assert ok and reason == ""


def test_no_safewords():
    assert SafetyGuard.contains_safeword("стоп красный stop") is False


def test_autonomy_whitelist():
    g = SafetyGuard(SafetyConfig(autonomy_level="observe"))
    tools = g.autonomy_tools()
    assert "camera_capture" in tools
    assert "xtoys_set_intensity" not in tools
    assert not SafetyGuard(SafetyConfig(autonomy_level="off")).autonomy_tools()


def test_session_never_blocks():
    g = SafetyGuard(SafetyConfig())
    g.start_session()
    ok, _ = g.session_check()
    assert ok
