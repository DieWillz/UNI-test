from __future__ import annotations

from typing import Any

from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY


def get_all_tool_definitions(
    enabled_capabilities: set[str] | None = None,
) -> list[dict[str, Any]]:
    """LLM tool schemas generated from UNI's canonical ActionRegistry."""
    return DEFAULT_ACTION_REGISTRY.tool_schemas(enabled_capabilities)


def get_tool_schemas(
    enabled_capabilities: set[str] | None = None,
) -> list[dict[str, Any]]:
    return get_all_tool_definitions(enabled_capabilities)
