from typing import List, Dict, Any
from .definitions import get_all_tool_definitions

def get_tool_schemas() -> List[Dict[str, Any]]:
    return get_all_tool_definitions()

class ToolRegistry:
    def __init__(self):
        self._tools = {}
        self._register_defaults()

    def _register_defaults(self):
        for t in get_all_tool_definitions():
            name = t["function"]["name"]
            self._tools[name] = t

    def get(self, name: str) -> Dict[str, Any]:
        return self._tools.get(name, {})

    def list(self) -> List[str]:
        return list(self._tools.keys())

    def get_schemas(self) -> List[Dict[str, Any]]:
        return list(self._tools.values())
