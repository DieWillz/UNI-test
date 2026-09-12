from __future__ import annotations

import pytest

from uni.agent import Agent


class _Registry:
    def get(self, name):
        return object() if name in {"computer", "vision"} else None


class _Executor:
    def set_control_mode(self, _mode):
        return object()

    def reset_control_mode(self, _token):
        pass


class _Logger:
    enabled = False


class _Speech:
    speak = None


@pytest.mark.asyncio
async def test_agent_passes_explicit_trajectory_sink_to_visual_agent(monkeypatch):
    captured = {}
    marker = object()

    class _Visual:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        async def act_on_screen(self, _goal, max_steps=8):
            return {"status": "failed", "steps": [], "error": "test"}

    monkeypatch.setattr("uni.agent.VisualActionAgent", _Visual)
    agent = Agent.__new__(Agent)
    agent.capabilities = _Registry()
    agent.tool_executor = _Executor()
    agent.session_logger = _Logger()
    agent.speech = _Speech()
    agent._trajectory_sink = marker

    await agent.act_on_screen("test goal", max_steps=1)

    assert captured["trajectory_sink"] is marker
