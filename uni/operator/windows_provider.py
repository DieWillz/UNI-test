from __future__ import annotations

import asyncio
from typing import Any

from uni.contracts import ToolResult
from uni.tools.executors import ToolExecutor

from .models import BoundingBox, SceneSnapshot, TargetSpec, UIElement
from .targeting import TargetAmbiguous, TargetNotFound, resolve_element


def _uia_element(index: int, raw: dict[str, Any]) -> UIElement:
    bbox = None
    width, height = float(raw.get("width") or 0), float(raw.get("height") or 0)
    if width > 0 and height > 0:
        bbox = BoundingBox(
            x=float(raw.get("x") or 0), y=float(raw.get("y") or 0),
            width=width, height=height,
        )
    metadata = {key: value for key, value in raw.items() if key not in {
        "name", "role", "text", "x", "y", "width", "height", "enabled", "value", "checked"
    }}
    return UIElement(
        ref=f"w{index}", source="uia", role=str(raw.get("role") or ""),
        name=str(raw.get("name") or ""), text=str(raw.get("text") or ""),
        bbox=bbox, enabled=bool(raw.get("enabled", True)), value=raw.get("value"),
        checked=raw.get("checked"), confidence=1.0, metadata=metadata,
    )


class WindowsProvider:
    def __init__(self, computer) -> None:
        self.computer = computer
        self.fallback_resolver = None

    async def inspect(self, *, limit: int = 120) -> SceneSnapshot:
        windows_result = await self.computer.execute("list_visible_windows")
        elements_result = await self.computer.execute("inspect_accessible_elements", max_elements=limit)
        if not elements_result.success:
            # Window/UIA trees can disappear during a focus transition. One fresh
            # retry only; never substitute stale elements or guessed coordinates.
            await asyncio.sleep(0.15)
            elements_result = await self.computer.execute("inspect_accessible_elements", max_elements=limit)
        windows = []
        if windows_result.success and isinstance(windows_result.data, dict):
            windows = list(windows_result.data.get("windows") or [])
        active_window: dict[str, Any] = {}
        raw_elements: list[dict[str, Any]] = []
        errors: list[str] = []
        if elements_result.success and isinstance(elements_result.data, dict):
            active_window = dict(elements_result.data.get("active_window") or {})
            raw_elements = list(elements_result.data.get("elements") or [])
        else:
            errors.append("uia_unavailable")
            detail = str(elements_result.error or elements_result.message or "unknown_error")[:500]
            errors.append("uia_detail: " + detail)
        return SceneSnapshot(
            active_window=active_window,
            windows=windows,
            elements=[_uia_element(i, item) for i, item in enumerate(raw_elements[:limit], 1)],
            errors=errors,
        )

    def resolve(self, target: TargetSpec, scene: SceneSnapshot) -> UIElement:
        return resolve_element(target, scene, source="uia")

    async def focus_matches(self, target: TargetSpec, *, hwnd: int) -> bool:
        """Require unique current UIA identity and an independent focused-name read.

        Existing ComputerCapability exposes focused name/value, not runtime ID.
        Reject duplicate names and window transitions instead of guessing.
        """
        if not hwnd:
            return False
        before = await self.inspect()
        element = self.resolve(target, before)
        if (before.errors or before.active_window.get("hwnd") != hwnd or not element.name
                or element.metadata.get("sensitive")
                or sum(item.name == element.name for item in before.elements) != 1):
            return False
        focused = await self.computer.execute("read_focused_accessible_text")
        if not focused.success or not isinstance(focused.data, dict):
            return False
        after = await self.inspect()
        current = self.resolve(target, after)
        return (not after.errors and after.active_window.get("hwnd") == hwnd
                and current.name == element.name == focused.data.get("name")
                and current.role == element.role
                and sum(item.name == current.name for item in after.elements) == 1)

    async def _click_element(self, element: UIElement) -> ToolResult:
        if element.bbox is None:
            return ToolResult(success=False, message="UIA target has no clickable rectangle")
        x = round(element.bbox.x + element.bbox.width / 2)
        y = round(element.bbox.y + element.bbox.height / 2)
        return await self.computer.execute("click_human", x=x, y=y, button="left")

    @staticmethod
    def _element_identity(element: UIElement) -> dict[str, Any]:
        params: dict[str, Any] = {"name": element.name, "control_type": element.role}
        automation_id = str(element.metadata.get("automation_id") or "").strip()
        if automation_id:
            params["automation_id"] = automation_id
        if element.bbox is not None:
            params.update(x=element.bbox.x, y=element.bbox.y,
                          width=element.bbox.width, height=element.bbox.height)
        return params

    async def _invoke_element(self, element: UIElement) -> ToolResult:
        if not element.name:
            return ToolResult(success=False, message="UIA target has no accessible name")
        return await self.computer.execute("invoke_accessible_element", **self._element_identity(element))

    async def act(self, action: str, *, target: TargetSpec | None = None, **params: Any) -> ToolResult:
        if action == "inspect":
            scene = await self.inspect()
            return ToolResult(success=True, data=scene.model_dump(mode="json"), message="UIA snapshot")
        if action == "launch":
            app = str(params.get("app") or (target.name if target else "")).strip()
            return await self.computer.execute("launch", app=app)
        if action == "focus":
            app = str(params.get("app") or (target.name if target else "")).strip()
            return await self.computer.execute("focus_app", app=app)
        if action == "press" and target is None:
            return await self.computer.execute("press", key=str(params.get("key", "")))
        if target is None:
            return ToolResult(success=False, message="target_required")
        scene = await self.inspect()
        try:
            element = self.resolve(target, scene)
        except TargetAmbiguous as exc:
            return ToolResult(success=False, message=str(exc), error=type(exc).__name__)
        except TargetNotFound as exc:
            if (target.ref or self.fallback_resolver is None
                    or action not in {"click", "fill", "press"}):
                return ToolResult(success=False, message=str(exc), error=type(exc).__name__)
            try:
                element = await self.fallback_resolver(target)
            except (TargetNotFound, TargetAmbiguous) as fallback_error:
                return ToolResult(success=False, message=str(fallback_error), error=type(fallback_error).__name__)
            if element.bbox is None or element.confidence < 0.8 or not element.enabled:
                return ToolResult(success=False, message="OCR/vision target is not confident enough for input")
        if action == "click":
            if ToolExecutor.mouse_only() or element.metadata.get("transient"):
                return await self._click_element(element)
            invoked = await self._invoke_element(element)
            return invoked  # A failed invocation may already have had an effect.
        if action == "read":
            if element.metadata.get("sensitive"):
                return ToolResult(success=False, message="sensitive_field_read_blocked")
            return ToolResult(success=True, message="fresh UIA element state", data={
                "ref": element.ref, "role": element.role, "name": element.name,
                "text": element.text, "value": element.value, "checked": element.checked,
                "enabled": element.enabled, "snapshot_id": scene.snapshot_id,
            })
        if action in {"check", "uncheck"}:
            identity = self._element_identity(element)
            identity["checked"] = action == "check"
            return await self.computer.execute("set_accessible_checked", **identity)
        if action == "select":
            identity = self._element_identity(element)
            identity["value"] = params.get("value")
            return await self.computer.execute("select_accessible_value", **identity)
        if action == "press":
            focused = await self._click_element(element)
            if not focused.success:
                return focused
            if not await self.focus_matches(target, hwnd=scene.active_window.get("hwnd", 0)):
                return ToolResult(success=False, message="keyboard_focus_not_verified")
            return await self.computer.execute("press", key=str(params.get("key", "")))
        if action != "fill":
            return ToolResult(success=False, message=f"unsupported_desktop_action: {action}")
        text = str(params.get("text", ""))
        if element.metadata.get("sensitive"):
            return ToolResult(success=False, message="sensitive_field_requires_explicit_handling")
        if element.name and not ToolExecutor.mouse_only() and not element.metadata.get("transient"):
            direct = await self.computer.execute("set_accessible_value", name=element.name, text=text)
            return direct  # Do not paste again after an uncertain set-value result.
        focused = await self._click_element(element)
        if not focused.success:
            return focused
        if not await self.focus_matches(target, hwnd=scene.active_window.get("hwnd", 0)):
            return ToolResult(success=False, message="keyboard_focus_not_verified")
        selected = await self.computer.execute("press", key="ctrl+a")
        if not selected.success:
            return selected
        if not await self.focus_matches(target, hwnd=scene.active_window.get("hwnd", 0)):
            return ToolResult(success=False, message="keyboard_focus_changed")
        return await self.computer.execute("paste", text=text)


__all__ = ["WindowsProvider", "TargetNotFound", "TargetAmbiguous"]
