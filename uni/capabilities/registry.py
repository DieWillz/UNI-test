"""Capability Registry"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]


class Capability:
    def __init__(self, name: str):
        self.name = name
        self._tools: dict[str, ToolSchema] = {}

    def register_tool(self, tool: ToolSchema) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolSchema | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSchema]:
        return list(self._tools.values())

    async def execute(self, tool_name: str, args: dict) -> Any:
        raise NotImplementedError

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class CapabilityRegistry:
    def __init__(self):
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def list(self) -> list[str]:
        return list(self._capabilities.keys())

    def all_tools(self) -> list[ToolSchema]:
        tools = []
        for cap in self._capabilities.values():
            tools.extend(cap.list_tools())
        return tools

    async def initialize_all(self) -> None:
        for cap in self._capabilities.values():
            await cap.initialize()

    async def shutdown_all(self) -> None:
        for cap in self._capabilities.values():
            await cap.shutdown()