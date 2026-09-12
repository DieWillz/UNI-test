from __future__ import annotations

import pytest

from uni.contracts import Evidence, TaskOutcome, TaskStatus, Verification, VerificationStatus
from uni.event_loop import EventLoop


class FakeAgent:
    def __init__(self, outcome):
        self.outcome = outcome
        self.goals = []
        self.stop_calls = 0

    async def run_operator(self, goal: str):
        self.goals.append(goal)
        return self.outcome

    def stop_operator(self):
        self.stop_calls += 1


def verified_outcome(goal: str) -> TaskOutcome:
    verification = Verification(
        status=VerificationStatus.VERIFIED,
        method="mission_postconditions",
        reason="verified",
        evidence=[Evidence(source="browser", summary="done")],
    )
    return TaskOutcome(command=goal, status=TaskStatus.VERIFIED,
                       message="mission done", verification=verification)


@pytest.mark.asyncio
async def test_complex_command_is_forwarded_to_operator_and_verification_is_reused() -> None:
    goal = "Открой браузер, найди Blender и скачай установщик"
    loop = object.__new__(EventLoop)
    agent = FakeAgent(verified_outcome(goal))
    loop._agent_ref = agent
    loop._current_actions = []
    loop._current_observations = []
    loop._current_verification = Verification()
    loop._log = lambda *_args, **_kwargs: None

    response = await loop._try_operator_mission(goal)

    assert response == "mission done"
    assert agent.goals == [goal]
    assert loop._current_verification.status is VerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_non_operator_conversation_returns_none_without_agent_call() -> None:
    loop = object.__new__(EventLoop)
    agent = FakeAgent(verified_outcome("unused"))
    loop._agent_ref = agent

    response = await loop._try_operator_mission("Что такое Playwright?")

    assert response is None
    assert agent.goals == []


def test_operator_stop_bridge_calls_agent_runtime() -> None:
    loop = object.__new__(EventLoop)
    agent = FakeAgent(verified_outcome("unused"))
    loop._agent_ref = agent

    loop._stop_operator_runtime()

    assert agent.stop_calls == 1


@pytest.mark.asyncio
async def test_run_cycle_stop_latches_operator_input() -> None:
    loop = object.__new__(EventLoop)
    agent = FakeAgent(verified_outcome("unused"))
    loop._agent_ref = agent
    loop._log = lambda *_args, **_kwargs: None
    loop._autonomous = lambda: None
    loop._speak = lambda _text: _async_true()
    loop.is_stop_command = lambda _text: True

    result = await loop.run_cycle(user_input="стоп")

    assert result == "stop"
    assert agent.stop_calls == 1


async def _async_true():
    return True
