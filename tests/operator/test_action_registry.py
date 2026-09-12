from __future__ import annotations

import pytest

from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY


def test_registry_is_single_source_for_route_and_llm_schema() -> None:
    spec = DEFAULT_ACTION_REGISTRY.get("browser.navigate")
    assert spec.capability == "browser"
    assert spec.action == "navigate"
    names = {
        item["function"]["name"]
        for item in DEFAULT_ACTION_REGISTRY.tool_schemas({"browser"})
    }
    assert "browser_navigate" in names


def test_dotted_and_api_alias_resolve_to_same_action() -> None:
    dotted = DEFAULT_ACTION_REGISTRY.get("browser.search_web")
    alias = DEFAULT_ACTION_REGISTRY.get("browser_search_web")
    assert dotted is alias


def test_duplicate_action_names_are_rejected() -> None:
    from uni.operator.action_registry import ActionRegistry, ActionSpec

    registry = ActionRegistry()
    spec = ActionSpec(
        name="demo.read",
        capability="demo",
        action="read",
        description="read demo",
    )
    registry.register(spec)
    with pytest.raises(ValueError):
        registry.register(spec)


def test_planner_catalog_contains_permission_and_verification_metadata() -> None:
    item = next(
        x for x in DEFAULT_ACTION_REGISTRY.planner_catalog()
        if x["name"] == "browser.navigate"
    )
    assert item["permission"] == "local_reversible"
    assert item["verification"] == "browser_location"
