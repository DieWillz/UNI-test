from __future__ import annotations

import pytest

from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY
from uni.operator.planner import MissionPlanner, PlanParseError


def test_parser_accepts_fenced_json_and_validates_actions() -> None:
    raw = '''```json
    {"goal":"open site","steps":[
      {"id":"open","action":"browser.navigate","params":{"url":"https://example.com"},
       "postcondition":{"kind":"browser_url_contains","params":{"text":"example.com"}}}
    ]}
    ```'''
    plan = MissionPlanner.parse_plan_text(raw, "open site", DEFAULT_ACTION_REGISTRY)
    assert plan.goal == "open site"
    assert plan.steps[0].action == "browser.navigate"


def test_parser_rejects_unregistered_action() -> None:
    raw = '{"goal":"x","steps":[{"id":"x","action":"shell.destroy"}]}'
    with pytest.raises(PlanParseError, match="unregistered_action"):
        MissionPlanner.parse_plan_text(raw, "x", DEFAULT_ACTION_REGISTRY)
