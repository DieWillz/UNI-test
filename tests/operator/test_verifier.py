from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uni.contracts import VerificationStatus
from uni.operator.models import PlanStep, Postcondition, SceneSnapshot, TargetSpec, UIElement
from uni.operator.verifier import PostconditionVerifier


def _fresh_browser(**extra):
    now = datetime.now(timezone.utc).isoformat()
    return {"session_id": "session-test", "tab_id": "tab-test", "snapshot_id": "snapshot-test",
            "observed_at": now, "timestamp": now, **extra}


@pytest.mark.asyncio
async def test_browser_url_is_verified_from_fresh_scene() -> None:
    verifier = PostconditionVerifier()
    step = PlanStep(id="s1", action="browser.navigate",
                    postcondition=Postcondition(kind="browser.url_contains", params={"text": "blender.org"}))
    scene = SceneSnapshot(browser=_fresh_browser(url="https://www.blender.org/download/", title="Blender"))

    result = await verifier.verify(step, scene=scene)

    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].source == "browser"


@pytest.mark.asyncio
async def test_element_value_uses_fresh_semantic_element() -> None:
    verifier = PostconditionVerifier()
    step = PlanStep(id="s1", action="operator.browser.fill",
                    target=TargetSpec(name="Search", role="textbox"),
                    postcondition=Postcondition(kind="element.value_equals", params={"value": "UNI"}))
    scene = SceneSnapshot(browser=_fresh_browser(), elements=[UIElement(
        ref="e1", source="dom", role="textbox", name="Search", value="UNI")])
    result = await verifier.verify(step, scene=scene)

    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].data["observed"] == "UNI"


@pytest.mark.asyncio
async def test_wrong_postcondition_is_not_verified() -> None:
    verifier = PostconditionVerifier()
    step = PlanStep(id="s1", action="operator.browser.click",
                    postcondition=Postcondition(kind="browser.title_contains", params={"text": "Settings"}))
    scene = SceneSnapshot(browser={"url": "https://x", "title": "Home"})

    result = await verifier.verify(step, scene=scene)

    assert result.status is VerificationStatus.NOT_VERIFIED
    assert result.evidence == []


@pytest.mark.asyncio
async def test_active_window_title_can_verify_launch() -> None:
    verifier = PostconditionVerifier()
    step = PlanStep(id="s1", action="operator.desktop.launch",
                    postcondition=Postcondition(kind="window.title_contains", params={"text": "Notepad"}))
    scene = SceneSnapshot(active_window={"title": "Untitled - Notepad", "pid": 101})

    result = await verifier.verify(step, scene=scene)

    assert result.status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_file_text_is_verified_by_fresh_read(tmp_path) -> None:
    from uni.operator.file_provider import FileProvider

    path = tmp_path / "result.txt"
    path.write_text("hello UNI", encoding="utf-8")
    verifier = PostconditionVerifier(file_provider=FileProvider())
    step = PlanStep(id="s1", action="operator.file.write_text",
                    postcondition=Postcondition(kind="file.text_contains",
                                                params={"path": str(path), "text": "UNI"}))

    result = await verifier.verify(step, scene=SceneSnapshot())

    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].source == "filesystem"


@pytest.mark.asyncio
async def test_file_absent_requires_fresh_exists_check(tmp_path) -> None:
    from uni.operator.file_provider import FileProvider

    path = tmp_path / "gone.txt"
    verifier = PostconditionVerifier(file_provider=FileProvider())
    step = PlanStep(id="s1", action="operator.file.delete",
                    postcondition=Postcondition(kind="file.absent", params={"path": str(path)}))

    result = await verifier.verify(step, scene=SceneSnapshot())

    assert result.status is VerificationStatus.VERIFIED
