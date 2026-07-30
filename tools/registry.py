"""Tool Registry - Maps tools to capabilities"""

from typing import Any
from .definitions import TOOLS, get_tool_by_name


# Tool -> Capability mapping
TOOL_CAPABILITY_MAP = {
    # Speech
    "listen": "speech",
    "speak": "speech",
    # Vision
    "analyze_screen": "vision",
    "find_element": "vision",
    "read_text": "vision",
    # Browser
    "navigate": "browser",
    "click_selector": "browser",
    "type_selector": "browser",
    "extract_text": "browser",
    "screenshot": "browser",
    "wait_for_selector": "browser",
    "get_page_info": "browser",
    # Computer
    "click": "computer",
    "type": "computer",
    "press": "computer",
    "move": "computer",
    "scroll": "computer",
    "screenshot_region": "computer",
    "focus_window": "computer",
    "get_window_list": "computer",
    # Memory
    "remember": "memory",
    "recall": "memory",
    "forget": "memory",
    "list_memory": "memory",
    "get_context": "memory",
}


class ToolRegistry:
    def __init__(self):
        self._tools = {tool.name: tool for tool in TOOLS}

    def get_tool(self, name: str):
        return self._tools.get(name)

    def get_capability_for_tool(self, tool_name: str) -> str | None:
        return TOOL_CAPABILITY_MAP.get(tool_name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools_for_capability(self, capability: str) -> list[str]:
        return [name for name, cap in TOOL_CAPABILITY_MAP.items() if cap == capability]

    def validate_args(self, tool_name: str, args: dict) -> tuple[bool, str | None]:
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"Unknown tool: {tool_name}"

        for param in tool.parameters:
            if param.required and param.name not in args:
                return False, f"Missing required parameter: {param.name}"
        return True, None