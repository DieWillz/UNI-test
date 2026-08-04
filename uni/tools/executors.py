from __future__ import annotations

from typing import Any

from uni.contracts import ToolResult


class ToolExecutor:
    _ROUTING = {
        "xtoys.open": ("xtoys", "open"),
        "xtoys.toggle": ("xtoys", "toggle"),
        "xtoys.set_intensity": ("xtoys", "set_intensity"),
        "xtoys.select_pattern": ("xtoys", "select_pattern"),
        "xtoys.get_status": ("xtoys", "get_status"),
        "browser.navigate": ("browser", "navigate"),
        "browser.search_web": ("browser", "search_web"),
        "browser.search_images": ("browser", "search_images"),
        "browser.click_selector": ("browser", "click_selector"),
        "browser.type_selector": ("browser", "type_selector"),
        "browser.extract_text": ("browser", "extract_text"),
        "browser.screenshot": ("browser", "screenshot"),
        "browser.save_screenshot": ("browser", "save_screenshot"),
        "browser.current_tab": ("browser", "current_tab"),
        "computer.launch": ("computer", "launch"),
        "computer.click": ("computer", "click"),
        "computer.type": ("computer", "type"),
        "computer.type_unicode": ("computer", "type_unicode"),
        "computer.press_window_hotkey": ("computer", "press_window_hotkey"),
        "computer.delete_backward": ("computer", "delete_backward"),
        "computer.paste": ("computer", "paste"),
        "computer.copy_selected_text": ("computer", "copy_selected_text"),
        "computer.focus_window": ("computer", "focus_window"),
        "computer.focus_app": ("computer", "focus_app"),
        "computer.find_accessible_element": ("computer", "find_accessible_element"),
        "computer.focus_accessible_element": ("computer", "focus_accessible_element"),
        "computer.read_accessible_value": ("computer", "read_accessible_value"),
        "computer.set_accessible_value": ("computer", "set_accessible_value"),
        "computer.replace_accessible_text": ("computer", "replace_accessible_text"),
        "computer.read_accessible_text": ("computer", "read_accessible_text"),
        "computer.read_focused_accessible_text": ("computer", "read_focused_accessible_text"),
        "computer.list_accessible_fields": ("computer", "list_accessible_fields"),
        "computer.list_visible_windows": ("computer", "list_visible_windows"),
        "computer.press": ("computer", "press"),
        "computer.click_human": ("computer", "click_human"),
        "computer.drag_human": ("computer", "drag_human"),
        "camera.start": ("camera", "start"),
        "camera.snapshot": ("camera", "snapshot"),
        "camera.stop": ("camera", "stop"),
        "speech.speak": ("speech", "speak"),
        "speech.listen": ("speech", "listen"),
        "speech.synthesize_file": ("speech", "synthesize_file"),
        "vision.analyze_screen": ("vision", "analyze_screen"),
        "vision.find_element": ("vision", "find_element"),
        "vision.analyze_desktop": ("vision", "analyze_desktop"),
        "vision.observe_desktop": ("vision", "observe_desktop"),
        "vision.find_desktop_element": ("vision", "find_desktop_element"),
        "vision.analyze_file": ("vision", "analyze_file"),
    }
    _API_ALIASES = {name.replace(".", "_"): name for name in _ROUTING}

    def __init__(self, capability_registry):
        self.registry = capability_registry

    @classmethod
    def canonical_name(cls, tool_name: str) -> str:
        return cls._API_ALIASES.get(tool_name, tool_name)

    async def execute(self, tool_name: str, args: dict[str, Any] | None = None) -> ToolResult:
        canonical = self.canonical_name(tool_name)
        route = self._ROUTING.get(canonical)
        if route is None:
            return ToolResult(success=False, message=f"Неизвестный инструмент: {tool_name}")
        capability_name, action = route
        capability = self.registry.get(capability_name)
        if capability is None:
            return ToolResult(success=False, message=f"Capability '{capability_name}' не зарегистрирована")
        try:
            result = await capability.execute(action, **(args or {}))
            if not isinstance(result, ToolResult):
                return ToolResult(success=False, message=f"{canonical} вернул некорректный результат")
            return result
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка {canonical}: {exc}")
