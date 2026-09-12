from __future__ import annotations

import pytest

from uni.contracts import ToolResult
from uni.operator.models import TargetSpec
from uni.operator.windows_provider import WindowsProvider


class FakeComputer:
    def __init__(self, *, invoke_success: bool = True):
        self.calls = []
        self.invoke_success = invoke_success

    async def execute(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if action == "list_visible_windows":
            return ToolResult(success=True, data={"windows":[
                {"title":"Notepad","executable":"notepad.exe","class_name":"Notepad","hwnd":11,"pid":22,"active":True}
            ]})
        if action == "inspect_accessible_elements":
            return ToolResult(success=True, data={"active_window":{"title":"Notepad","hwnd":11,"pid":22}, "elements":[
                {"name":"File","role":"menu_item","x":10,"y":10,"width":50,"height":20,"enabled":True,"automation_id":"file"},
                {"name":"Save","role":"button","x":80,"y":10,"width":60,"height":20,"enabled":True,"automation_id":"save"},
                {"name":"Document","role":"textbox","x":10,"y":50,"width":400,"height":300,"enabled":True,"value":""},
            ]})
        if action == "invoke_accessible_element":
            return ToolResult(success=self.invoke_success, message="invoke")
        return ToolResult(success=True, message="ok", data=kwargs)


@pytest.mark.asyncio
async def test_windows_snapshot_produces_uia_refs() -> None:
    provider = WindowsProvider(FakeComputer())
    scene = await provider.inspect()
    assert scene.active_window["title"] == "Notepad"
    assert scene.elements[2].source == "uia"
    assert scene.elements[2].ref == "w3"


@pytest.mark.asyncio
async def test_fill_prefers_accessible_set_value() -> None:
    computer = FakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("fill", target=TargetSpec(name="Document", role="textbox"), text="UNI test")
    assert result.success is True
    assert ("set_accessible_value", {"name":"Document", "text":"UNI test"}) in computer.calls


def _invoke_call(computer: FakeComputer):
    return next(kwargs for action, kwargs in computer.calls if action == "invoke_accessible_element")


@pytest.mark.asyncio
async def test_click_prefers_uia_invoke_for_button() -> None:
    computer = FakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("click", target=TargetSpec(name="Save", role="button"))
    assert result.success is True
    invoke = _invoke_call(computer)
    assert invoke["name"] == "Save"
    assert invoke["control_type"] == "button"
    assert invoke["automation_id"] == "save"
    assert not any(action == "click_human" for action, _ in computer.calls)


@pytest.mark.asyncio
async def test_click_falls_back_to_fresh_bbox_when_uia_invoke_fails() -> None:
    computer = FakeComputer(invoke_success=False)
    provider = WindowsProvider(computer)
    result = await provider.act("click", target=TargetSpec(name="File", role="menu_item"))
    assert result.success is True
    invoke = _invoke_call(computer)
    assert invoke["name"] == "File"
    assert invoke["control_type"] == "menu_item"
    assert invoke["automation_id"] == "file"
    assert ("click_human", {"x":35, "y":20, "button":"left"}) in computer.calls


class RichFakeComputer(FakeComputer):
    async def execute(self, action, **kwargs):
        if action == "inspect_accessible_elements":
            self.calls.append((action, kwargs))
            return ToolResult(success=True, data={
                "active_window":{"title":"Settings","hwnd":33,"pid":44},
                "elements":[
                    {"name":"Remember me","role":"checkbox","x":10,"y":10,"width":100,"height":20,"enabled":True,"checked":False,"automation_id":"remember"},
                    {"name":"Theme","role":"combobox","x":10,"y":40,"width":140,"height":25,"enabled":True,"value":"Dark","automation_id":"theme"},
                    {"name":"Status","role":"text","x":10,"y":80,"width":120,"height":20,"enabled":True,"text":"Ready"},
                ],
            })
        return await super().execute(action, **kwargs)


@pytest.mark.asyncio
async def test_read_returns_fresh_semantic_state_without_physical_input() -> None:
    computer = RichFakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("read", target=TargetSpec(name="Theme", role="combobox"))
    assert result.success is True
    assert result.data["value"] == "Dark"
    assert result.data["role"] == "combobox"
    assert not any(action in {"click_human", "press", "paste"} for action, _ in computer.calls)


@pytest.mark.asyncio
async def test_check_prefers_uia_toggle_to_desired_state() -> None:
    computer = RichFakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("check", target=TargetSpec(name="Remember me", role="checkbox"))
    assert result.success is True
    calls = [kwargs for action, kwargs in computer.calls if action == "set_accessible_checked"]
    assert calls and calls[-1]["checked"] is True
    assert calls[-1]["automation_id"] == "remember"


@pytest.mark.asyncio
async def test_uncheck_prefers_uia_toggle_to_desired_state() -> None:
    computer = RichFakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("uncheck", target=TargetSpec(name="Remember me", role="checkbox"))
    assert result.success is True
    calls = [kwargs for action, kwargs in computer.calls if action == "set_accessible_checked"]
    assert calls and calls[-1]["checked"] is False


@pytest.mark.asyncio
async def test_select_prefers_uia_selection_pattern() -> None:
    computer = RichFakeComputer()
    provider = WindowsProvider(computer)
    result = await provider.act("select", target=TargetSpec(name="Theme", role="combobox"), value="Light")
    assert result.success is True
    calls = [kwargs for action, kwargs in computer.calls if action == "select_accessible_value"]
    assert calls and calls[-1]["value"] == "Light"
    assert calls[-1]["automation_id"] == "theme"
