from typing import Any, Dict
from uni.contracts import ToolResult

class ToolExecutor:
    _ROUTING = {
        "xtoys_toggle": ("xtoys", "toggle"),
        "xtoys_set_intensity": ("xtoys", "set_intensity"),
        "xtoys_select_pattern": ("xtoys", "select_pattern"),
        "xtoys_get_status": ("xtoys", "get_status"),
        "browser_navigate": ("browser", "navigate"),
        "browser_click_selector": ("browser", "click_selector"),
        "browser_type_selector": ("browser", "type_selector"),
        "computer_launch": ("computer", "launch"),
        "computer_click": ("computer", "click"),
        "computer_type": ("computer", "type"),
        "computer_press": ("computer", "press"),
        "speech_speak": ("speech", "speak"),
        "speech_listen": ("speech", "listen"),
        "vision_analyze_screen": ("vision", "analyze_screen"),
    }

    def __init__(self, capability_registry):
        self.registry = capability_registry

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        if tool_name not in self._ROUTING:
            return ToolResult(success=False, message=f"Неизвестный инструмент: {tool_name}")
        cap_name, action = self._ROUTING[tool_name]
        cap = self.registry.get(cap_name)
        if not cap:
            return ToolResult(success=False, message=f"Capability '{cap_name}' не зарегистрирована")
        try:
            return await cap.execute(action, **args)
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка {tool_name}: {e}")
