from __future__ import annotations

from pathlib import Path

from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.tools.definitions import get_all_tool_definitions
from uni.tools.executors import ToolExecutor


def test_tool_definitions_are_generated_from_canonical_registry() -> None:
    assert get_all_tool_definitions({"browser"}) == DEFAULT_ACTION_REGISTRY.tool_schemas({"browser"})


def test_executor_canonicalization_uses_same_registry() -> None:
    assert ToolExecutor.canonical_name("browser_search_web") == "browser.search_web"
    assert ToolExecutor.canonical_name("browser.search_web") == "browser.search_web"


def test_no_second_manual_routing_table_remains() -> None:
    root = Path(__file__).resolve().parents[2]
    executor_source = (root / "uni" / "tools" / "executors.py").read_text(encoding="utf-8")
    definitions_source = (root / "uni" / "tools" / "definitions.py").read_text(encoding="utf-8")
    assert "_ROUTING =" not in executor_source
    assert "DEFAULT_ACTION_REGISTRY" in definitions_source
