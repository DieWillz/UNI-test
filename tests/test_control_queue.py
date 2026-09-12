from __future__ import annotations

import pytest

from uni.capabilities.xtoys import XToysCapability
from uni.control_queue import ControlQueue, QueueOperation
from uni.xtoys_control_coordinator import ToyControlCoordinator


class FakeCoordinator:
    def __init__(self):
        self.current_value = 0
        self.calls: list[tuple[str, int]] = []
        self.emergency_calls = 0

    async def set_intensity(self, source: str, value: int) -> bool:
        self.calls.append((source, int(value)))
        self.current_value = int(value)
        return True

    async def emergency_stop(self) -> bool:
        self.emergency_calls += 1
        self.current_value = 0
        return True


class DummySession:
    async def page_for_host(self, *_args, **_kwargs):
        raise AssertionError("Dorch must never use browser DOM for device motion")

@pytest.mark.asyncio
async def test_replace_all_counts_only_replacement_horizon():
    q = ControlQueue(coordinator=FakeCoordinator(), max_intensity=65, allowed=lambda: True)
    q.stopped = False
    first = await q.apply(QueueOperation(
        operation="append",
        items=[{"type": "hold", "intensity_percent": 10, "duration_seconds": 2000}],
    ))
    assert first["accepted"] is True

    result = await q.apply(QueueOperation(
        operation="replace_all",
        items=[{"type": "hold", "intensity_percent": 20, "duration_seconds": 2000}],
    ))
    assert result["accepted"] is True
    assert len(result["steps"]) == 1
    assert result["steps"][0]["intensity_percent"] == 20


@pytest.mark.asyncio
async def test_replace_pending_counts_running_plus_new_not_old_pending():
    q = ControlQueue(coordinator=FakeCoordinator(), max_intensity=65, allowed=lambda: True)
    q.stopped = False
    await q.apply(QueueOperation(
        operation="append",
        items=[{"type": "hold", "intensity_percent": 10, "duration_seconds": 2000}],
    ))
    result = await q.apply(QueueOperation(
        operation="replace_pending",
        items=[{"type": "hold", "intensity_percent": 30, "duration_seconds": 2000}],
    ))
    assert result["accepted"] is True
    assert len(result["steps"]) == 1
    assert result["steps"][0]["intensity_percent"] == 30

@pytest.mark.asyncio
async def test_xtoys_positive_manual_command_needs_no_verified_physical_ack():
    coordinator = FakeCoordinator()
    capability = XToysCapability(DummySession(), url="https://xtoys.app", max_intensity=65)
    capability.coordinator = coordinator

    result = await capability.set_intensity(value=25)

    assert result.success is True
    assert coordinator.calls == [("manual", 25)]
    assert result.data["requested_percent"] == 25
    assert result.data["verified_physical"] is False


@pytest.mark.asyncio
async def test_queue_rejects_power_above_hard_max():
    q = ControlQueue(coordinator=FakeCoordinator(), max_intensity=65, allowed=lambda: True)
    result = await q.apply(QueueOperation(
        operation="append",
        items=[{"type": "hold", "intensity_percent": 80, "duration_seconds": 10}],
    ))
    assert result["accepted"] is False
    assert "max_intensity" in result["error"]


@pytest.mark.asyncio
async def test_stop_latches_queue_and_sends_zero():
    coordinator = FakeCoordinator()
    q = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    q.stopped = False
    result = await q.apply(QueueOperation(operation="stop"))
    assert result["accepted"] is True
    assert q.stopped is True
    assert q.mode == "stopped"
    assert coordinator.emergency_calls == 1


def test_agent_autonomous_gate_uses_persistent_config_not_runtime_ack():
    from uni import agent as agent_module
    from uni.config import Config

    gate = getattr(agent_module, "autonomous_device_allowed", None)
    assert callable(gate), "Agent needs one canonical persistent-config Dorch gate"
    cfg = Config()
    cfg.autonomous.enabled = True
    cfg.capabilities.xtoys.autonomous_physical = True
    assert gate(cfg) is True
    cfg.autonomous.enabled = False
    assert gate(cfg) is False


@pytest.mark.asyncio
async def test_reset_stop_does_not_relatch_emergency_on_new_plan():
    coordinator = FakeCoordinator()
    q = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    q.stopped = False
    await q.apply(QueueOperation(operation="stop"))
    assert coordinator.emergency_calls == 1

    q.reset_stop()
    result = await q.apply(QueueOperation(
        operation="replace_all",
        items=[{"type": "hold", "intensity_percent": 10, "duration_seconds": 5}],
    ))

    assert result["accepted"] is True
    assert coordinator.emergency_calls == 1


@pytest.mark.asyncio
async def test_manual_override_cancels_autonomous_plan_without_latching_stop():
    class FakeIntiface:
        def __init__(self):
            self.values: list[int] = []

        async def oscillate(self, value: int) -> dict:
            value = int(value)
            self.values.append(value)
            return {
                "ok": True,
                "value": value,
                "device": "Synthetic test device",
                "feature": "Oscillate",
                "steps": 20,
            }

    bridge = FakeIntiface()
    coordinator = ToyControlCoordinator(bridge)
    coordinator.configure_autonomous(lambda: True)
    queue = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    queue.reset_stop()
    plan = await queue.apply(QueueOperation(
        operation="replace_all",
        items=[{"type": "hold", "intensity_percent": 40, "duration_seconds": 60}],
    ))
    plan_step_id = plan["steps"][0]["id"]
    await queue.run_once()
    assert coordinator.active_source == "autonomous"
    assert coordinator.current_value == 40

    result = await queue.manual_override(25)

    assert next(step for step in queue.steps if step.id == plan_step_id).status == "cancelled"
    assert result["mode"] == "manual"
    assert result["stopped"] is False
    assert coordinator.active_source == "manual"
    assert coordinator.current_value == 25
    assert bridge.values[-1] == 25
    assert coordinator.emergency_stopped is False


@pytest.mark.asyncio
async def test_remove_pending_revises_only_when_an_existing_pending_step_is_removed():
    queue = ControlQueue(coordinator=FakeCoordinator(), max_intensity=65, allowed=lambda: True)
    appended = await queue.apply(QueueOperation(
        operation="append",
        items=[
            {"type": "hold", "intensity_percent": 10, "duration_seconds": 60},
            {"type": "hold", "intensity_percent": 20, "duration_seconds": 60},
        ],
    ))
    running_id, pending_id = (step["id"] for step in appended["steps"])
    queue.steps[0].status = "running"
    revision_before_removal = queue.queue_revision

    removed = await queue.apply(QueueOperation(
        operation="remove_pending",
        items=[{"step_id": pending_id}],
    ))

    assert removed["accepted"] is True
    assert queue.queue_revision == revision_before_removal + 1
    assert [(step.id, step.status) for step in queue.steps] == [(running_id, "running")]

    rejected_running = await queue.apply(QueueOperation(
        operation="remove_pending",
        items=[{"step_id": running_id}],
    ))
    rejected_unknown = await queue.apply(QueueOperation(
        operation="remove_pending",
        items=[{"step_id": "step_unknown"}],
    ))

    assert rejected_running["accepted"] is False
    assert rejected_unknown["accepted"] is False
    assert queue.queue_revision == revision_before_removal + 1
    assert [(step.id, step.status) for step in queue.steps] == [(running_id, "running")]
