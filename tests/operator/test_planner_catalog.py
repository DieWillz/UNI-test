from __future__ import annotations

import json

from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.planner import MissionPlanner


def test_planner_catalog_hides_legacy_selectors_and_raw_coordinates() -> None:
    planner = MissionPlanner(brain=None, registry=DEFAULT_ACTION_REGISTRY)
    names = {item["name"] for item in json.loads(planner._catalog_text())}

    assert "browser.click_selector" not in names
    assert "browser.type_selector" not in names
    assert "computer.click" not in names
    assert "computer.click_human" not in names
    assert "operator.browser.click" in names
    assert "operator.desktop.click" in names


def test_semantic_action_specs_describe_target_and_action_parameters() -> None:
    click = DEFAULT_ACTION_REGISTRY.get("operator.browser.click")
    fill = DEFAULT_ACTION_REGISTRY.get("operator.browser.fill")
    download = DEFAULT_ACTION_REGISTRY.get("operator.browser.download")
    write = DEFAULT_ACTION_REGISTRY.get("operator.file.write_text")

    assert click.requires_target is True
    assert fill.requires_target is True
    assert fill.required == ("text",)
    assert download.required == ("path",)
    assert write.required == ("path", "text")


def test_planner_catalog_exposes_semantic_windows_state_actions() -> None:
    planner = MissionPlanner(brain=None, registry=DEFAULT_ACTION_REGISTRY)
    names = {item["name"] for item in json.loads(planner._catalog_text())}

    assert "operator.desktop.read" in names
    assert "operator.desktop.check" in names
    assert "operator.desktop.uncheck" in names
    assert "operator.desktop.select" in names

    read = DEFAULT_ACTION_REGISTRY.get("operator.desktop.read")
    check = DEFAULT_ACTION_REGISTRY.get("operator.desktop.check")
    select = DEFAULT_ACTION_REGISTRY.get("operator.desktop.select")
    assert read.requires_target is True
    assert check.requires_target is True
    assert select.requires_target is True
    assert select.required == ("value",)
