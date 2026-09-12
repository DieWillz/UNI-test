from __future__ import annotations

import pytest

from uni.operator.browser_provider import BrowserProvider, TargetNotFound, TargetAmbiguous
from uni.operator.models import TargetSpec


class FakeDOM:
    def __init__(self):
        self.calls = []

    async def inspect(self, limit=100):
        return {
            "snapshot_id": "s1", "browser": {"url": "https://x", "title": "X"},
            "elements": [
                {"ref":"e1","source":"dom","role":"button","name":"Download","text":"Download now","confidence":1.0},
                {"ref":"e2","source":"dom","role":"link","name":"Downloads","text":"Downloads","confidence":1.0},
            ], "errors": [],
        }

    async def act(self, action, **params):
        self.calls.append((action, params))
        return {"status":"not_verified", "action":action}


class FakeSession:
    def __init__(self):
        self.operator_dom = FakeDOM()


@pytest.mark.asyncio
async def test_exact_semantic_name_beats_partial_text() -> None:
    provider = BrowserProvider(FakeSession())
    scene = await provider.inspect()
    element = provider.resolve(TargetSpec(name="Download", role="button"), scene)
    assert element.ref == "e1"


@pytest.mark.asyncio
async def test_click_uses_ref_from_fresh_snapshot_not_model_selector() -> None:
    session = FakeSession()
    provider = BrowserProvider(session)
    result = await provider.act("click", target=TargetSpec(name="Download", role="button"))
    assert result["status"] == "not_verified"
    action, params = session.operator_dom.calls[-1]
    assert action == "click_ref"
    assert params["ref"] == "e1"
    assert params["snapshot_id"] == "s1"


def test_missing_and_ambiguous_targets_fail_closed() -> None:
    provider = BrowserProvider(FakeSession())
    from uni.operator.models import SceneSnapshot, UIElement
    scene = SceneSnapshot(snapshot_id="s", elements=[])
    with pytest.raises(TargetNotFound):
        provider.resolve(TargetSpec(name="Nope"), scene)
    scene = SceneSnapshot(snapshot_id="s", elements=[
        UIElement(ref="a", source="dom", name="OK"), UIElement(ref="b", source="dom", name="OK")])
    with pytest.raises(TargetAmbiguous):
        provider.resolve(TargetSpec(name="OK", exact=True), scene)


@pytest.mark.asyncio
async def test_bare_ref_cannot_bind_to_next_snapshot() -> None:
    provider = BrowserProvider(FakeSession())
    await provider.inspect()
    with pytest.raises(ValueError, match="snapshot_id_required"):
        await provider.act("click", target=TargetSpec(ref="e1"))
    assert provider.session.operator_dom.calls == []


@pytest.mark.asyncio
async def test_raw_selector_is_rejected_before_dom_call() -> None:
    provider = BrowserProvider(FakeSession())
    with pytest.raises(ValueError, match="unsupported_browser_parameter"):
        await provider.act("click", target=TargetSpec(name="Download"), selector="#delete")
    assert provider.session.operator_dom.calls == []


def test_disabled_or_other_source_cannot_be_acted_on() -> None:
    from uni.operator.models import SceneSnapshot, UIElement
    provider = BrowserProvider(FakeSession())
    scene = SceneSnapshot(elements=[
        UIElement(ref="e1", source="dom", role="button", name="Save", enabled=False),
        UIElement(ref="u1", source="uia", role="button", name="Save"),
    ])
    with pytest.raises(TargetNotFound):
        provider.resolve(TargetSpec(name="Save"), scene)
    with pytest.raises(TargetNotFound):
        provider.resolve(TargetSpec(ref="u1"), scene)


def test_name_matches_visible_text_when_accessible_name_differs() -> None:
    from uni.operator.models import SceneSnapshot, UIElement
    provider = BrowserProvider(FakeSession())
    scene = SceneSnapshot(elements=[
        UIElement(ref="e1", source="dom", role="button", name="Save this file", text="Save"),
        UIElement(ref="e2", source="dom", role="button", name="Save now", text="Other"),
    ])
    assert provider.resolve(TargetSpec(name="Save"), scene).ref == "e1"


def test_active_dialog_excludes_background_match() -> None:
    from uni.operator.models import SceneSnapshot, UIElement
    provider = BrowserProvider(FakeSession())
    scene = SceneSnapshot(browser={"active_dialog": "Upload"}, elements=[
        UIElement(ref="e1", source="dom", role="button", name="Save"),
        UIElement(ref="e2", source="dom", role="button", name="Save", metadata={"in_dialog": True}),
    ])
    assert provider.resolve(TargetSpec(name="Save"), scene).ref == "e2"


@pytest.mark.asyncio
async def test_page_scroll_is_not_rewritten_as_element_scroll() -> None:
    session = FakeSession()
    provider = BrowserProvider(session)
    await provider.act("scroll", delta_y=600)
    action, params = session.operator_dom.calls[-1]
    assert action == "scroll"
    assert not params.get("ref")


@pytest.mark.asyncio
async def test_semantic_missing_recovery_has_bounded_scrolls() -> None:
    provider = BrowserProvider(FakeSession())
    with pytest.raises(TargetNotFound):
        await provider.act("click", target=TargetSpec(name="Missing"), scroll_budget=2)
    calls = provider.session.operator_dom.calls
    assert len(calls) == 2
    assert all(action == "scroll" for action, params in calls)


@pytest.mark.asyncio
async def test_assert_mismatch_is_not_a_successful_read_action() -> None:
    session = FakeSession()
    async def mismatch(action, **params):
        return {"assertion_passed": False, "status": "not_verified"}
    session.operator_dom.act = mismatch
    with pytest.raises(ValueError, match="browser_assertion_failed"):
        await BrowserProvider(session).act("assert", target=TargetSpec(name="Download"),
                                           property="text", equals="Saved")


@pytest.mark.asyncio
async def test_wait_reobserves_delayed_target_without_replaying_input() -> None:
    session = FakeSession()
    original = session.operator_dom.inspect
    observations = 0
    async def delayed(**kwargs):
        nonlocal observations
        observations += 1
        raw = await original(**kwargs)
        if observations < 2:
            raw["elements"] = []
        return raw
    session.operator_dom.inspect = delayed
    result = await BrowserProvider(session).act("wait", target=TargetSpec(name="Download"), milliseconds=400)
    assert result["element"]["ref"] == "e1"
    assert observations >= 2
    assert session.operator_dom.calls == []


@pytest.mark.asyncio
async def test_wait_timeout_stops_without_input():
    session = FakeSession()
    with pytest.raises(TimeoutError, match="browser_wait_timeout"):
        await BrowserProvider(session).act("wait", target=TargetSpec(name="Missing"), milliseconds=0)
    assert session.operator_dom.calls == []
