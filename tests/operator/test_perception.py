from __future__ import annotations

import pytest

from uni.contracts import ToolResult
from uni.operator.models import SceneSnapshot, TargetSpec, UIElement
from uni.operator.perception import PerceptionBroker
from uni.operator.browser_provider import TargetNotFound


class Browser:
    async def inspect(self):
        return SceneSnapshot(snapshot_id="b", browser={"url":"https://x"}, elements=[
            UIElement(ref="e1", source="dom", role="button", name="DOM button")])


class Windows:
    async def inspect(self):
        return SceneSnapshot(snapshot_id="w", active_window={"title":"App"}, windows=[{"title":"App"}], elements=[
            UIElement(ref="w1", source="uia", role="button", name="UIA button")])
    def resolve(self, target, scene):
        for item in scene.elements:
            if target.name.casefold() in item.name.casefold():
                return item
        raise TargetNotFound("target_not_found")


class Vision:
    def __init__(self): self.calls = []
    async def execute(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return ToolResult(success=True, data={"x":100,"y":120,"width":50,"height":20,"confidence":0.8})


@pytest.mark.asyncio
async def test_observe_merges_browser_and_windows_without_vlm() -> None:
    vision = Vision()
    broker = PerceptionBroker(Browser(), Windows(), vision=vision, ocr_finder=lambda _: None)
    scene = await broker.observe()
    assert {e.source for e in scene.elements} == {"dom", "uia"}
    assert scene.browser["url"] == "https://x"
    assert scene.active_window["title"] == "App"
    assert vision.calls == []


@pytest.mark.asyncio
async def test_desktop_resolution_prefers_uia_then_ocr_then_vlm() -> None:
    vision = Vision()
    broker = PerceptionBroker(Browser(), Windows(), vision=vision,
        ocr_finder=lambda text: {"x":1,"y":2,"width":30,"height":10,"confidence":0.7,"source":"ocr"})
    uia = await broker.resolve_desktop(TargetSpec(name="UIA button"))
    assert uia.source == "uia"
    ocr = await broker.resolve_desktop(TargetSpec(name="Only OCR"))
    assert ocr.source == "ocr"
    assert vision.calls == []


@pytest.mark.asyncio
async def test_vlm_is_last_fallback() -> None:
    vision = Vision()
    broker = PerceptionBroker(Browser(), Windows(), vision=vision, ocr_finder=lambda _: None)
    element = await broker.resolve_desktop(TargetSpec(name="Vision only"))
    assert element.source == "vision"
    assert vision.calls[0][0] == "find_desktop_element"
