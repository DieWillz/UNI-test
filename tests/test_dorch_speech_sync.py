from __future__ import annotations

import pytest

from uni.control_queue import ControlQueue, QueueOperation


class FakeCoordinator:
    def __init__(self, accept: bool = True):
        self.accept = accept
        self.current_value = 0
        self.calls = []

    async def set_intensity(self, source: str, value: int) -> bool:
        self.calls.append((source, int(value)))
        if self.accept:
            self.current_value = int(value)
        return self.accept

    async def emergency_stop(self) -> bool:
        self.current_value = 0
        return True


@pytest.mark.asyncio
async def test_step_speech_event_is_emitted_only_after_command_is_accepted():
    coordinator = FakeCoordinator(accept=True)
    events = []
    q = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    q.stopped = False
    q.set_execution_callback(events.append)
    await q.apply(QueueOperation(operation="append", items=[{
        "type": "hold", "intensity_percent": 25, "duration_seconds": 5,
        "speech": "Сейчас держу двадцать пять процентов.",
    }]))

    assert events == []
    await q.run_once()

    assert coordinator.calls[-1] == ("autonomous", 25)
    assert [e["type"] for e in events] == ["step_applied"]
    assert events[0]["speech"] == "Сейчас держу двадцать пять процентов."
    assert events[0]["commanded_value"] == 25


@pytest.mark.asyncio
async def test_rejected_command_emits_failure_not_motion_speech():
    coordinator = FakeCoordinator(accept=False)
    events = []
    q = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    q.stopped = False
    q.set_execution_callback(events.append)
    await q.apply(QueueOperation(operation="append", items=[{
        "type": "hold", "intensity_percent": 30, "duration_seconds": 5,
        "speech": "Я подняла мощность до тридцати процентов.",
    }]))

    await q.run_once()

    assert [e["type"] for e in events] == ["step_failed"]
    assert events[0]["commanded_value"] == 30
    assert events[0]["speech"] == ""
    assert "не принята" in events[0]["message"].casefold()


class FakeSpeech:
    def __init__(self):
        self.lines = []

    async def speak(self, text):
        self.lines.append(text)
        return True


class FakeBrain:
    def __init__(self, reply: str):
        self.reply = reply
        self.prompts = []

    async def simple_chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


class FakeRegistry:
    def __init__(self, speech):
        self.speech = speech

    def get(self, name):
        return self.speech if name == "speech" else None


@pytest.mark.asyncio
async def test_autonomous_planner_builds_structured_queue_operation_from_model_json():
    import json
    from types import SimpleNamespace
    from uni.autonomous import AutonomousController
    from uni.config import Config

    speech = FakeSpeech()
    brain = FakeBrain(json.dumps({
        "operation": "append",
        "items": [{
            "type": "hold", "intensity_percent": 22, "duration_seconds": 4,
            "speech": "Держу двадцать два процента.",
        }],
        "reason": "continue",
    }))
    agent = SimpleNamespace(brain=brain, capabilities=FakeRegistry(speech), toy_coordinator=None)
    ctrl = AutonomousController(agent, Config(), control_queue=object())

    planner = getattr(ctrl, "_plan_control_operation", None)
    assert callable(planner), "AutonomousController needs structured ControlQueue planning"
    op = await planner({"mode": "autonomous", "steps": [], "max_intensity": 50})

    assert op.operation == "append"
    assert op.items[0]["intensity_percent"] == 22
    assert op.items[0]["speech"] == "Держу двадцать два процента."


@pytest.mark.asyncio
async def test_autonomous_speaks_applied_step_and_reports_failed_step_truthfully():
    from types import SimpleNamespace
    from uni.autonomous import AutonomousController
    from uni.config import Config

    speech = FakeSpeech()
    agent = SimpleNamespace(brain=FakeBrain("{}"), capabilities=FakeRegistry(speech), toy_coordinator=None)
    ctrl = AutonomousController(agent, Config(), control_queue=object())
    published = []

    async def publish(text):
        published.append(text)
    ctrl._emit_phrase = publish

    handler = getattr(ctrl, "handle_control_event", None)
    assert callable(handler), "AutonomousController needs a queue execution event handler"

    await handler({"type": "step_applied", "speech": "Теперь двадцать пять процентов.", "commanded_value": 25})
    await handler({"type": "step_failed", "speech": "Я подняла мощность.", "commanded_value": 30,
                   "message": "Intiface: команда не принята"})

    assert published[0] == "Теперь двадцать пять процентов."
    assert speech.lines[0] == "Теперь двадцать пять процентов."
    assert "не принята" in published[1].casefold()
    assert "я подняла мощность" not in published[1].casefold()


def test_queue_status_exposes_current_and_pending_speech():
    import asyncio

    async def scenario():
        q = ControlQueue(coordinator=FakeCoordinator(), max_intensity=65, allowed=lambda: True)
        q.stopped = False
        await q.apply(QueueOperation(operation="append", items=[{
            "type": "hold", "intensity_percent": 15, "duration_seconds": 5,
            "speech": "Первый шаг.",
        }, {
            "type": "hold", "intensity_percent": 20, "duration_seconds": 5,
            "speech": "Следующий шаг.",
        }]))
        await q.run_once()
        return q.status()

    status = asyncio.run(scenario())
    assert status["current_step"]["speech"] == "Первый шаг."
    assert status["pending_steps"][0]["speech"] == "Следующий шаг."
