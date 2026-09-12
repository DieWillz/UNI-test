from __future__ import annotations

import pytest

from uni.operator.models import (
    MissionPlan,
    PlanStep,
    Postcondition,
    SceneSnapshot,
    TargetSpec,
    UIElement,
)


def test_scene_elements_have_stable_refs_and_source() -> None:
    element = UIElement(ref="e1", source="dom", role="button", name="Download")
    scene = SceneSnapshot(snapshot_id="s1", elements=[element])
    assert scene.elements[0].ref == "e1"
    assert scene.elements[0].source == "dom"


def test_target_spec_requires_some_semantic_identity() -> None:
    with pytest.raises(ValueError):
        TargetSpec()


def test_plan_requires_unique_step_ids_and_known_dependencies() -> None:
    steps = [
        PlanStep(id="open", action="browser.navigate"),
        PlanStep(id="read", action="browser.extract_text", dependencies=["open"]),
    ]
    plan = MissionPlan(goal="read page", steps=steps)
    assert [step.id for step in plan.steps] == ["open", "read"]
    with pytest.raises(ValueError):
        MissionPlan(goal="bad", steps=[
            PlanStep(id="x", action="browser.navigate"),
            PlanStep(id="x", action="browser.current_tab"),
        ])
    with pytest.raises(ValueError):
        MissionPlan(goal="bad", steps=[
            PlanStep(id="x", action="browser.navigate", dependencies=["missing"]),
        ])


def test_postcondition_is_explicit_not_implicit_success() -> None:
    step = PlanStep(
        id="save",
        action="computer.press",
        params={"key": "ctrl+s"},
        postcondition=Postcondition(kind="file_exists", params={"path": r"C:\tmp\x.txt"}),
    )
    assert step.postcondition.kind == "file_exists"
