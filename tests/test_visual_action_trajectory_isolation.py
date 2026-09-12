from __future__ import annotations

import pytest

from uni.contracts import ToolResult
from uni.tools.visual_action import VisualActionAgent


class _Computer:
    use_human_motion = False

    async def click(self, x, y):
        return ToolResult(success=True, message="clicked")


class _Vision:
    async def find_desktop_element(self, _query):
        return ToolResult(success=True, data={
            "x": 100, "y": 100, "width": 80, "height": 30, "confidence": 0.9,
        })

    async def analyze_desktop(self, _prompt):
        return ToolResult(success=True, data={"analysis": "да"})


@pytest.mark.asyncio
async def test_visual_action_has_no_implicit_global_trajectory_write(tmp_path, monkeypatch):
    from uni.tools import trajectory_store

    target = tmp_path / "trajectories.jsonl"
    monkeypatch.setattr(trajectory_store, "_TRAJ_DIR", tmp_path)
    monkeypatch.setattr(trajectory_store, "_TRAJ_PATH", target)
    monkeypatch.setattr("uni.tools.local_vision_fallback.find_desktop_element_tier0", lambda _goal: None)

    agent = VisualActionAgent(_Computer(), _Vision(), verify_delay=0)
    result = await agent.act_on_screen("unique synthetic test goal", max_steps=1)

    assert result["status"] == "verified"
    assert not target.exists()


@pytest.mark.asyncio
async def test_visual_action_records_only_through_explicit_sink(monkeypatch):
    calls = []
    monkeypatch.setattr("uni.tools.local_vision_fallback.find_desktop_element_tier0", lambda _goal: None)

    def sink(goal, steps, history, *, status):
        calls.append((goal, list(steps), list(history), status))

    agent = VisualActionAgent(_Computer(), _Vision(), verify_delay=0, trajectory_sink=sink)
    result = await agent.act_on_screen("explicit recorded goal", max_steps=1)

    assert result["status"] == "verified"
    assert len(calls) == 1
    assert calls[0][0] == "explicit recorded goal"
    assert calls[0][3] == "verified"
