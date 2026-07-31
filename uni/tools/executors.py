"""Tool Executor - dispatches tool calls to capabilities"""

from typing import Any
from ..capabilities.registry import CapabilityRegistry
from ..tools.definitions import get_capability_for_tool


class ToolExecutor:
    def __init__(self, capabilities: CapabilityRegistry):
        self.capabilities = capabilities

    async def execute(self, tool_name: str, args: dict) -> dict:
        """Execute a tool by dispatching to the appropriate capability."""
        capability_name = get_capability_for_tool(tool_name)
        if not capability_name:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        capability = self.capabilities.get(capability_name)
        if not capability:
            return {"success": False, "error": f"Capability not available: {capability_name}"}

        try:
            result = await capability.execute(tool_name, args)
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_available_tools(self) -> list[str]:
        """List all available tools."""
        from ..tools.definitions import TOOL_DEFINITIONS
        return [tool.name for tool in TOOL_DEFINITIONS]