"""P0 browser execution recovery regressions (owner directive 2026-09-12).

RED -> GREEN. These tests lock the architectural fixes:
- planner context budget (task-specific catalog + compact scene + hard cap)
- CDP attach failure must not stop the task (managed launch fallback)
- focus -> type flow must be valid; click-with-value on a textbox stays rejected
- TTS failure must not break the browser task
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uni.config import Config
from uni.contracts import ToolResult
from uni.event_loop import EventLoop
from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.planner import MissionPlanner, PlanParseError


BROWSER_GOAL = "открой новую вкладку и набери там coral.ru"
MOUSE_GOAL = "используй мышку и открой новую вкладку"

# Legacy/test contract: _catalog_text() with no args stays full (used by other tests).
FULL_CATALOG = MissionPlanner(None)._catalog_text()


def _browser_scene() -> dict:
    return {
        "active_window": {"title": "Chrome"},
        "windows": [{"title": "Chrome", "executable": "chrome.exe"}],
        "browser": {"url": "https://example.com/", "title": "Example", "tab_id": "tab-1", "session_id": "browser-1"},
        "elements": [{"ref": "w1", "source": "uia", "role": "textbox", "name": "Address",
                      "text": "", "bbox": {"x": 1, "y": 2, "width": 600, "height": 30},
                      "confidence": 1.0} for _ in range(60)],
        "errors": [],
    }


class RecordingBrain:
    def __init__(self, text: str = "{}"):
        self.text = text
        self.messages: list[dict] | None = None

    async def chat(self, messages, **kwargs):
        self.messages = messages
        return SimpleNamespace(error=None, text=self.text, tool_calls=[])


def _estimate_tokens(text: str) -> int:
    # Conservative Cyrillic-aware heuristic (~1 token per 2.2 chars for mixed text).
    return int(len(text) / 2.2)


# ---------------------------------------------------------------- planner budget

def test_planner_browser_catalog_is_task_specific() -> None:
    planner = MissionPlanner(None)
    catalog = planner._catalog_text(scope="browser")
    names = {item["name"] for item in json.loads(catalog)}
    # browser-relevant actions must be present
    for required in ("operator.browser.new_tab", "operator.browser.fill", "operator.browser.press",
                     "operator.desktop.focus", "browser.navigate"):
        assert required in names, f"missing {required} in browser catalog"
    # irrelevant subsystems must be absent (tiny prompt is the whole point)
    for forbidden in ("xtoys", "camera", "operator.file.delete", "speech."):
        assert not any(forbidden in name for name in names), f"unexpected {forbidden} in browser catalog"
    # the browser catalog must be far smaller than the full catalog
    assert len(catalog) < len(FULL_CATALOG) // 2, (
        f"browser catalog not compact: {len(catalog)} chars vs full {len(FULL_CATALOG)}"
    )
    # and compact enough to fit the planner budget comfortably
    assert _estimate_tokens(catalog) < 1500, _estimate_tokens(catalog)


def test_planner_simple_browser_command_fits_context_budget() -> None:
    # Structural, loop-free budget check: the exact prompt plan() builds must be small.
    planner = MissionPlanner(None)
    system = planner._system_prompt(scope="browser")
    user = planner._user_prompt(BROWSER_GOAL, scene=_browser_scene(), scope="browser", failure_context="")
    total_tokens = _estimate_tokens(system + user)
    assert total_tokens < 4200, f"planner prompt too large: {total_tokens} tokens"
    assert BROWSER_GOAL in user, "current user command must be preserved verbatim"
    assert "coral.ru" in user


def test_planner_regular_catalog_still_full_for_legacy_callers() -> None:
    # Backward compatibility: no-arg _catalog_text() stays the full catalog.
    names = {item["name"] for item in json.loads(FULL_CATALOG)}
    assert "operator.desktop.fill" in names
    assert "operator.browser.new_tab" in names


# ------------------------------------------------------------- focus -> type flow

def _plan_with(steps: list[dict]) -> str:
    return json.dumps({"goal": BROWSER_GOAL, "steps": steps}, ensure_ascii=False)


def test_validator_accepts_focus_then_fill_then_press_flow() -> None:
    raw = _plan_with([
        {"id": "1", "action": "operator.desktop.focus", "params": {"app": "chrome"},
         "postcondition": {"kind": "window.title_contains", "params": {"text": "Chrome"}},
         "retry_budget": 0, "dependencies": []},
        {"id": "2", "action": "operator.desktop.press", "params": {"key": "ctrl+t"},
         "postcondition": {"kind": "window.title_contains", "params": {"text": "Chrome"}},
         "retry_budget": 0, "dependencies": ["1"]},
        {"id": "3", "action": "operator.desktop.fill",
         "params": {"text": "coral.ru"},
         "target": {"name": "Address", "source": "uia"},
         "postcondition": {"kind": "element.value_equals", "params": {"value": "coral.ru"}},
         "retry_budget": 0, "dependencies": ["2"]},
        {"id": "4", "action": "operator.desktop.press", "params": {"key": "enter"},
         "postcondition": {"kind": "browser.url_contains", "params": {"text": "coral.ru"}},
         "retry_budget": 0, "dependencies": ["3"]},
    ])
    plan = MissionPlanner.parse_plan_text(raw, BROWSER_GOAL, DEFAULT_ACTION_REGISTRY)
    assert [step.action for step in plan.steps] == [
        "operator.desktop.focus", "operator.desktop.press",
        "operator.desktop.fill", "operator.desktop.press",
    ]


def test_validator_still_rejects_click_with_value_on_textbox() -> None:
    raw = _plan_with([
        {"id": "1", "action": "operator.desktop.click",
         "params": {}, "target": {"name": "Address", "role": "textbox", "source": "uia"},
         "postcondition": {"kind": "element.value_equals", "params": {"value": "coral.ru"}},
         "retry_budget": 0, "dependencies": []},
    ])
    # resolve_element needs a real SceneSnapshot; the click-with-value check only
    # fires when the target resolves to a textbox.
    from uni.operator.models import SceneSnapshot, BoundingBox, UIElement
    scene = SceneSnapshot(
        active_window={"title": "Chrome"},
        windows=[{"title": "Chrome", "executable": "chrome.exe"}],
        elements=[UIElement(ref="w1", source="uia", role="textbox", name="Address",
                            bbox=BoundingBox(x=1, y=2, width=600, height=30))],
    )
    with pytest.raises(PlanParseError, match="click_cannot_fill_text_field"):
        MissionPlanner.parse_plan_text(raw, BROWSER_GOAL, DEFAULT_ACTION_REGISTRY, scene=scene)


# --------------------------------------------------------- CDP failure fallback

@pytest.mark.asyncio
async def test_browser_session_start_falls_back_when_cdp_attach_fails() -> None:
    from uni.browser_session import BrowserSession

    fake_context = MagicMock()
    fake_context.pages = [MagicMock()]
    fake_context.new_page = AsyncMock(return_value=fake_context.pages[0])

    fake_chromium = MagicMock()
    fake_chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("cdp dead"))
    fake_chromium.launch_persistent_context = AsyncMock(return_value=fake_context)

    fake_playwright = MagicMock()
    fake_playwright.start = AsyncMock(return_value=fake_playwright)
    fake_playwright.stop = AsyncMock()
    fake_playwright.chromium = fake_chromium

    session = BrowserSession(cdp_url="http://127.0.0.1:9222", headless=True, agent_cursor_enabled=False)
    with patch("uni.browser_session.async_playwright", return_value=fake_playwright):
        await session.start()

    # CDP attach failed, but the session must NOT have raised: managed launch fallback ran.
    fake_chromium.launch_persistent_context.assert_awaited_once()
    assert session._context is fake_context
    assert session._owns_context is True


@pytest.mark.asyncio
async def test_browser_session_start_raises_when_everything_fails() -> None:
    # When CDP attach AND managed launch both fail, the session must surface the
    # real launch reason (factual, not a synthetic CDP-only code). This keeps the
    # CDP-unavailable fallback real instead of masking the terminal failure.
    from uni.browser_session import BrowserSession

    fake_chromium = MagicMock()
    fake_chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("cdp dead"))
    fake_chromium.launch_persistent_context = AsyncMock(side_effect=RuntimeError("launch dead"))

    fake_playwright = MagicMock()
    fake_playwright.start = AsyncMock(return_value=fake_playwright)
    fake_playwright.stop = AsyncMock()
    fake_playwright.chromium = fake_chromium

    session = BrowserSession(cdp_url="http://127.0.0.1:9222", headless=True, agent_cursor_enabled=False)
    with patch("uni.browser_session.async_playwright", return_value=fake_playwright):
        with pytest.raises(RuntimeError, match="launch dead"):
            await session.start()


# -------------------------------------------------------------- TTS isolation

class _ExplodingTTSExecutor:
    def canonical_name(self, name):
        return name

    async def execute(self, name, args=None):
        if name == "speech.speak":
            raise RuntimeError("Piper не вернул аудио")
        return ToolResult(success=True, message="ok")


@pytest.mark.asyncio
async def test_tts_failure_does_not_raise_and_returns_false() -> None:
    config = Config()
    config.agent.speak_responses = True
    loop = EventLoop(
        brain=None,
        capabilities=SimpleNamespace(get_names=lambda: []),
        memory=SimpleNamespace(get_context=lambda: "", set=lambda *_: None),
        tool_executor=_ExplodingTTSExecutor(),
        config=config,
    )

    # After TTS explosion the loop is still usable and _speak returns False.
    assert await loop._speak("Привет") is False