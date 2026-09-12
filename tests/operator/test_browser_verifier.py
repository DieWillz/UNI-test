from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from uni.contracts import VerificationStatus
from uni.operator.models import PlanStep, Postcondition, SceneSnapshot, TargetSpec, UIElement
from uni.operator.verifier import PostconditionVerifier


def _time(seconds: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _scene(*, elements=(), **browser) -> SceneSnapshot:
    return SceneSnapshot(
        browser={
            "session_id": "session-1", "tab_id": "tab-1", "snapshot_id": "dom-fresh",
            "timestamp": _time(), "observed_at": _time(), "complete": True,
            "elements_complete": True, "tabs_complete": True,
            "url": "https://example.test/settings", "title": "Settings",
            "tabs": [{"tab_id": "tab-1", "url": "https://example.test/settings", "title": "Settings"}],
            **browser,
        },
        elements=list(elements),
    )


def _step(kind: str, params=None, *, target=None, action="operator.browser.click", action_params=None):
    return PlanStep(id="s1", action=action, params=action_params or {}, target=target,
                    postcondition=Postcondition(kind=kind, params=params or {}))


def _receipt(action: str, **extra):
    return {
        "id": "receipt-1", "action": action, "session_id": "session-1",
        "source_tab_id": "tab-1", "before_snapshot_id": "dom-before",
        "started_at": _time(-2), "completed_at": _time(-1),
        "before_tabs": [{"tab_id": "tab-1", "url": "https://example.test/settings", "title": "Settings"}],
        **extra,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,params", [
    ("browser.url_equals", {"value": "https://example.test/settings"}),
    ("browser.url_contains", {"text": "example.test"}),
    ("browser.title_equals", {"value": "Settings"}),
    ("browser.title_contains", {"text": "SETTINGS"}),
])
async def test_browser_location_uses_explicit_fresh_scoped_observation(kind, params):
    result = await PostconditionVerifier().verify(_step(kind, params), scene=_scene())
    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].data["session_id"] == "session-1"
    assert result.evidence[0].data["tab_id"] == "tab-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("browser", [
    {"observed_at": _time(-120)}, {"observed_at": "invalid"}, {"session_id": ""},
    {"tab_id": ""}, {"observed_at": _time(120)},
    {"last_action": _receipt("click", session_id="other-session")},
    {"last_action": _receipt("click", completed_at=_time(3600))},
    {"last_action": _receipt("click", before_snapshot_id="dom-fresh")},
])
async def test_browser_location_rejects_stale_missing_or_mismatched_scope(browser):
    result = await PostconditionVerifier().verify(
        _step("browser.title_equals", {"value": "Settings"}), scene=_scene(**browser))
    assert result.status is VerificationStatus.NOT_VERIFIED
    assert not result.evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,params", [
    ("browser.fake_equals", {"value": "Settings"}),
    ("browser.title_equals", {}),
    ("browser.url_equals", {"value": "", "tab_id": "tab-2"}),
])
async def test_unknown_or_unscoped_conditions_do_not_fall_through_to_title(kind, params):
    result = await PostconditionVerifier().verify(_step(kind, params), scene=_scene())
    assert result.status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,params,changes", [
    ("element.exists", {}, {}), ("element.enabled", {}, {}),
    ("element.disabled", {}, {"enabled": False}),
    ("element.text_contains", {"text": "saved"}, {"text": "Changes saved"}),
    ("element.text_equals", {"value": "Saved"}, {"text": "Saved"}),
    ("element.value_equals", {"value": "UNI"}, {"value": "UNI"}),
    ("element.checked_equals", {"value": True}, {"checked": True}),
])
async def test_browser_elements_use_fresh_dom_values(kind, params, changes):
    element = UIElement(ref="dom-new", source="dom", name="Result", role="textbox",
                        **{"enabled": True, **changes})
    step = _step(kind, params, target=TargetSpec(name="Result", role="textbox", exact=True))
    result = await PostconditionVerifier().verify(step, scene=_scene(elements=[element]))
    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].data["snapshot_id"] == "dom-fresh"


@pytest.mark.asyncio
async def test_browser_postcondition_target_can_differ_from_action_target():
    element = UIElement(ref="notice", source="dom", name="Saved", role="status", text="Saved")
    step = _step("browser.element.text_equals", {
        "target": {"name": "Saved", "role": "status", "exact": True}, "value": "Saved",
    }, target=TargetSpec(name="Save", role="button"))
    result = await PostconditionVerifier().verify(step, scene=_scene(elements=[element]))
    assert result.status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
@pytest.mark.parametrize("elements", [
    [UIElement(ref="uia", source="uia", name="Result", role="textbox", value="UNI")],
    [UIElement(ref="d1", source="dom", name="Result", role="textbox", value="UNI"),
     UIElement(ref="d2", source="dom", name="Result", role="textbox", value="UNI")],
])
async def test_browser_element_rejects_non_dom_and_ambiguous_candidates(elements):
    result = await PostconditionVerifier().verify(
        _step("element.value_equals", {"value": "UNI"}, target=TargetSpec(name="Result", role="textbox")),
        scene=_scene(elements=elements))
    assert result.status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_browser_missing_requires_complete_scene_and_semantic_identity():
    verifier = PostconditionVerifier()
    step = _step("element.missing", target=TargetSpec(name="Old dialog", role="dialog", exact=True))
    result = await verifier.verify(step, scene=_scene())
    assert result.status is VerificationStatus.VERIFIED
    for scene in (_scene(elements_complete=False), _scene(complete=False)):
        assert (await verifier.verify(step, scene=scene)).status is VerificationStatus.NOT_VERIFIED
    ref_only = _step("element.missing", target=TargetSpec(ref="old-ref"))
    assert (await verifier.verify(ref_only, scene=_scene())).status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_browser_errors_do_not_make_missing_true():
    scene = _scene()
    scene.errors.append("dom_unavailable")
    result = await PostconditionVerifier().verify(
        _step("element.missing", target=TargetSpec(name="Save")), scene=scene)
    assert result.status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_tab_appeared_requires_fresh_transition_not_existing_matching_tab():
    before = [{"tab_id": "tab-1", "title": "Settings", "url": "https://example.test/settings"}]
    after = before + [{"tab_id": "tab-2", "title": "Report", "url": "https://example.test/report"}]
    step = _step("browser.tab_appeared", {"title": "Report"}, action="operator.browser.new_tab")
    verifier = PostconditionVerifier()
    scene = _scene(last_action=_receipt("new_tab", before_tabs=before), tabs=after)
    assert (await verifier.verify(step, scene=scene)).status is VerificationStatus.VERIFIED
    scene.browser["last_action"]["before_tabs"] = after
    assert (await verifier.verify(step, scene=scene)).status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_tab_disappeared_needs_present_baseline_and_complete_current_tabs():
    step = _step("browser.tab_disappeared", {"tab_id": "tab-2"}, action="operator.browser.close_tab")
    before = [{"tab_id": "tab-1"}, {"tab_id": "tab-2"}]
    verifier = PostconditionVerifier()
    scene = _scene(last_action=_receipt("close_tab", before_tabs=before))
    assert (await verifier.verify(step, scene=scene)).status is VerificationStatus.VERIFIED
    scene.browser["tabs_complete"] = False
    assert (await verifier.verify(step, scene=scene)).status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_download_needs_browser_event_and_independent_fresh_file_stat(tmp_path):
    path = tmp_path / "download.txt"
    path.write_text("downloaded data", encoding="utf-8")
    stat = path.stat()
    receipt = _receipt("download", download_event={
        "url": "https://example.test/file", "suggested_filename": "download.txt", "failure": None,
    }, file_observation={"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                         "observed_at": _time(-1)})
    step = _step("browser.download_completed", {"path": str(path)},
                 action="operator.browser.download", action_params={"path": str(path)})
    verifier = PostconditionVerifier()
    assert (await verifier.verify(step, scene=_scene(last_action=receipt))).status is VerificationStatus.VERIFIED
    path.write_text("changed after action", encoding="utf-8")
    assert (await verifier.verify(step, scene=_scene(last_action=receipt))).status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["no_event", "failed", "other_session", "other_tab", "empty", "missing"])
async def test_download_cannot_be_verified_by_receipt_or_file_alone(tmp_path, change):
    path = tmp_path / "download.txt"
    path.write_text("" if change == "empty" else "data", encoding="utf-8")
    stat = path.stat()
    receipt = _receipt("download", download_event={"url": "https://example.test/file", "failure": None},
                       file_observation={"path": str(path), "size": stat.st_size,
                                         "mtime_ns": stat.st_mtime_ns, "observed_at": _time(-1)})
    if change == "no_event":
        receipt.pop("download_event")
    elif change == "failed":
        receipt["download_event"]["failure"] = "cancelled"
    elif change == "other_session":
        receipt["session_id"] = "other"
    elif change == "other_tab":
        receipt["source_tab_id"] = "other"
    elif change == "missing":
        path.unlink()
    step = _step("browser.download_completed", {"path": str(path)},
                 action="operator.browser.download", action_params={"path": str(path)})
    result = await PostconditionVerifier().verify(step, scene=_scene(last_action=receipt))
    assert result.status is VerificationStatus.NOT_VERIFIED
    assert not result.evidence


@pytest.mark.asyncio
async def test_nonbrowser_element_verification_is_unchanged():
    step = _step("element.value_equals", {"value": "UNI"}, action="operator.desktop.fill",
                 target=TargetSpec(name="Search", role="textbox"))
    scene = SceneSnapshot(elements=[UIElement(ref="uia-1", source="uia", name="Search",
                                              role="textbox", value="UNI")])
    assert (await PostconditionVerifier().verify(step, scene=scene)).status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_default_model_fields_are_not_observations_of_enabled_or_empty_text():
    scene = _scene(elements=[UIElement(ref="dom", source="dom", name="Result")])
    for kind, params in (("element.enabled", {}), ("element.text_equals", {"value": ""})):
        result = await PostconditionVerifier().verify(
            _step(kind, params, target=TargetSpec(name="Result")), scene=scene)
        assert result.status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_old_action_receipt_cannot_be_reused_in_fresh_scene():
    receipt = _receipt("click", started_at=_time(-180), completed_at=_time(-120))
    result = await PostconditionVerifier().verify(
        _step("browser.title_equals", {"value": "Settings"}), scene=_scene(last_action=receipt))
    assert result.status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_tab_transition_honors_requested_session():
    scene = _scene(last_action=_receipt("new_tab"), tabs=[{"tab_id": "tab-1"}, {"tab_id": "tab-2"}])
    step = _step("browser.tab_appeared", {"tab_id": "tab-2", "session_id": "other"},
                 action="operator.browser.new_tab")
    assert (await PostconditionVerifier().verify(step, scene=scene)).status is VerificationStatus.NOT_VERIFIED


@pytest.mark.asyncio
async def test_new_snapshot_cannot_rebind_old_ref_without_semantic_target():
    scene = _scene(elements=[UIElement(ref="e1", source="dom", name="Wrong new element")])
    step = _step("element.exists", target=TargetSpec(ref="e1"))
    assert (await PostconditionVerifier().verify(step, scene=scene)).status is VerificationStatus.NOT_VERIFIED
    semantic = _step("element.exists", target=TargetSpec(ref="expired", name="Wrong new element"))
    assert (await PostconditionVerifier().verify(semantic, scene=scene)).status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_browser_alias_action_matches_canonical_receipt():
    step = _step("browser.title_equals", {"value": "Settings"}, action="browser.click_ref")
    result = await PostconditionVerifier().verify(step, scene=_scene(last_action=_receipt("click")))
    assert result.status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_new_popup_tab_can_be_active_after_click():
    scene = _scene(tab_id="popup", last_action=_receipt("click"),
                   tabs=[{"tab_id": "tab-1"}, {"tab_id": "popup", "title": "Report"}])
    step = _step("browser.tab_appeared", {"title": "Report"})
    assert (await PostconditionVerifier().verify(step, scene=scene)).status is VerificationStatus.VERIFIED
