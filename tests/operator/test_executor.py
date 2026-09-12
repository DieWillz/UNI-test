from __future__ import annotations

from types import SimpleNamespace

import pytest

from uni.contracts import TaskStatus, ToolResult
from uni.operator.action_registry import ActionRegistry, ActionSpec
from uni.operator.executor import MissionExecutor
from uni.operator.models import MissionPlan, PermissionLevel, PlanStep, Postcondition, SceneSnapshot
from uni.operator.permissions import MissionPermissions


class StaticPlanner:
    def __init__(self, plan: MissionPlan):
        self.plan_value = plan
        self.calls = 0

    async def plan(self, goal, **_kwargs):
        self.calls += 1
        return self.plan_value


class SequencePerception:
    def __init__(self, *scenes: SceneSnapshot):
        self.scenes = list(scenes) or [SceneSnapshot()]
        self.calls = 0

    async def observe(self):
        index = min(self.calls, len(self.scenes) - 1)
        self.calls += 1
        return self.scenes[index]


class FakeToolExecutor:
    def __init__(self, result: ToolResult):
        self.result = result
        self.calls = []

    async def execute(self, name, args):
        self.calls.append((name, args))
        return self.result


def build_registry(*, permission=PermissionLevel.LOCAL_REVERSIBLE, physical=False) -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(ActionSpec(
        name="demo.set", capability="demo", action="set", description="demo",
        permission=permission, side_effect=True, physical_input=physical,
    ))
    return registry


def plan_for_title(title: str, *, retry_budget: int = 0) -> MissionPlan:
    return MissionPlan(goal="set demo", steps=[PlanStep(
        id="s1", action="demo.set", params={"value": 1}, retry_budget=retry_budget,
        postcondition=Postcondition(kind="window.title_contains", params={"text": title}),
    )])


@pytest.mark.asyncio
async def test_successful_action_is_verified_only_after_fresh_scene() -> None:
    registry = build_registry()
    tool = FakeToolExecutor(ToolResult(success=True, message="sent"))
    perception = SequencePerception(
        SceneSnapshot(active_window={"title": "Home"}),
        SceneSnapshot(active_window={"title": "Done"}),
    )
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=perception, tool_executor=tool, registry=registry)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.VERIFIED
    assert len(tool.calls) == 1
    assert outcome.verification.evidence[0].source == "uia"


@pytest.mark.asyncio
async def test_action_success_without_postcondition_match_is_not_success() -> None:
    registry = build_registry()
    tool = FakeToolExecutor(ToolResult(success=True, message="sent"))
    perception = SequencePerception(SceneSnapshot(active_window={"title": "Home"}))
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=perception, tool_executor=tool, registry=registry)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.NOT_VERIFIED
    assert outcome.is_success is False


@pytest.mark.asyncio
async def test_already_satisfied_postcondition_skips_side_effect() -> None:
    registry = build_registry()
    tool = FakeToolExecutor(ToolResult(success=True, message="should not run"))
    perception = SequencePerception(SceneSnapshot(active_window={"title": "Done"}))
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=perception, tool_executor=tool, registry=registry)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.VERIFIED
    assert tool.calls == []


@pytest.mark.asyncio
async def test_critical_action_is_blocked_without_mission_approval() -> None:
    registry = build_registry(permission=PermissionLevel.CRITICAL)
    tool = FakeToolExecutor(ToolResult(success=True, message="should not run"))
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=SequencePerception(SceneSnapshot()),
                               tool_executor=tool, registry=registry)

    outcome = await executor.run("set demo", permissions=MissionPermissions())

    assert outcome.status is TaskStatus.BLOCKED
    assert tool.calls == []


class BrokerAwareToolExecutor(FakeToolExecutor):
    def __init__(self, broker):
        super().__init__(ToolResult(success=True, message="sent"))
        self.broker = broker
        self.owners = []

    async def execute(self, name, args):
        self.owners.append(self.broker.owner)
        return await super().execute(name, args)


@pytest.mark.asyncio
async def test_physical_action_holds_exclusive_input_lease() -> None:
    from uni.operator.input_broker import InputBroker

    broker = InputBroker()
    registry = build_registry(physical=True)
    tool = BrokerAwareToolExecutor(broker)
    perception = SequencePerception(
        SceneSnapshot(active_window={"title": "Home"}),
        SceneSnapshot(active_window={"title": "Done"}),
    )
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=perception, tool_executor=tool,
                               registry=registry, input_broker=broker)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.VERIFIED
    assert tool.owners and tool.owners[0]
    assert broker.owner is None


@pytest.mark.asyncio
async def test_stopped_input_interrupts_physical_mission_before_action() -> None:
    from uni.operator.input_broker import InputBroker

    broker = InputBroker()
    broker.stop()
    registry = build_registry(physical=True)
    tool = BrokerAwareToolExecutor(broker)
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=SequencePerception(SceneSnapshot()),
                               tool_executor=tool, registry=registry, input_broker=broker)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.INTERRUPTED
    assert tool.calls == []


@pytest.mark.asyncio
async def test_stopped_input_interrupts_nonphysical_mission_before_action() -> None:
    from uni.operator.input_broker import InputBroker

    broker = InputBroker()
    broker.stop()
    registry = build_registry(physical=False)
    tool = FakeToolExecutor(ToolResult(success=True, message="should not run"))
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title("Done")),
                               perception=SequencePerception(SceneSnapshot()),
                               tool_executor=tool, registry=registry, input_broker=broker)

    outcome = await executor.run("set demo")

    assert outcome.status is TaskStatus.INTERRUPTED
    assert tool.calls == []

class SlowToolExecutor(FakeToolExecutor):
    def __init__(self):
        super().__init__(ToolResult(success=True, message='late'))
        import asyncio
        self.started = asyncio.Event()
        self.cancelled = False

    async def execute(self, name, args):
        import asyncio
        self.calls.append((name, args))
        self.started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


@pytest.mark.asyncio
async def test_stop_interrupts_inflight_nonphysical_action() -> None:
    import asyncio
    from uni.operator.input_broker import InputBroker

    broker = InputBroker()
    registry = build_registry(physical=False)
    tool = SlowToolExecutor()
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title('Done')),
                               perception=SequencePerception(SceneSnapshot()),
                               tool_executor=tool, registry=registry, input_broker=broker)

    task = asyncio.create_task(executor.run('set demo'))
    await asyncio.wait_for(tool.started.wait(), timeout=0.5)
    broker.stop()
    outcome = await asyncio.wait_for(task, timeout=0.5)

    assert outcome.status is TaskStatus.INTERRUPTED
    assert tool.cancelled is True


@pytest.mark.asyncio
async def test_stop_interrupts_inflight_planning() -> None:
    import asyncio
    from uni.operator.input_broker import InputBroker

    class SlowPlanner:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def plan(self, goal, **_kwargs):
            self.started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return plan_for_title("Done")

    broker = InputBroker()
    planner = SlowPlanner()
    executor = MissionExecutor(planner=planner,
                               perception=SequencePerception(SceneSnapshot()),
                               tool_executor=FakeToolExecutor(ToolResult(success=True, message="unused")),
                               registry=build_registry(physical=False), input_broker=broker)

    task = asyncio.create_task(executor.run("slow plan"))
    await asyncio.wait_for(planner.started.wait(), timeout=0.5)
    broker.stop()
    outcome = await asyncio.wait_for(task, timeout=0.5)

    assert outcome.status is TaskStatus.INTERRUPTED
    assert planner.cancelled is True


@pytest.mark.asyncio
async def test_stop_interrupts_inflight_initial_observation() -> None:
    import asyncio
    from uni.operator.input_broker import InputBroker

    class SlowPerception:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def observe(self):
            self.started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return SceneSnapshot()

    broker = InputBroker()
    perception = SlowPerception()
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title('Done')), perception=perception,
        tool_executor=FakeToolExecutor(ToolResult(success=True, message='unused')),
        registry=build_registry(), input_broker=broker)
    task = asyncio.create_task(executor.run('slow observe'))
    await asyncio.wait_for(perception.started.wait(), timeout=0.5)
    broker.stop()
    outcome = await asyncio.wait_for(task, timeout=0.5)
    assert outcome.status is TaskStatus.INTERRUPTED
    assert perception.cancelled is True


@pytest.mark.asyncio
async def test_stop_interrupts_post_action_observation() -> None:
    import asyncio
    from uni.operator.input_broker import InputBroker

    class SlowAfterActionPerception:
        def __init__(self) -> None:
            self.calls = 0
            self.started = asyncio.Event()
            self.cancelled = False

        async def observe(self):
            self.calls += 1
            if self.calls == 1:
                return SceneSnapshot(active_window={'title': 'Home'})
            self.started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return SceneSnapshot(active_window={'title': 'Done'})

    broker = InputBroker()
    perception = SlowAfterActionPerception()
    executor = MissionExecutor(planner=StaticPlanner(plan_for_title('Done')), perception=perception,
        tool_executor=FakeToolExecutor(ToolResult(success=True, message='sent')),
        registry=build_registry(), input_broker=broker)
    task = asyncio.create_task(executor.run('set demo'))
    await asyncio.wait_for(perception.started.wait(), timeout=0.5)
    broker.stop()
    outcome = await asyncio.wait_for(task, timeout=0.5)
    assert outcome.status is TaskStatus.INTERRUPTED
    assert perception.cancelled is True


@pytest.mark.asyncio
async def test_stop_interrupts_inflight_post_action_verification() -> None:
    import asyncio
    from uni.contracts import Verification, VerificationStatus
    from uni.operator.input_broker import InputBroker

    class SlowSecondVerifier:
        def __init__(self) -> None:
            self.calls = 0
            self.started = asyncio.Event()
            self.cancelled = False

        async def verify(self, _step, *, scene):
            self.calls += 1
            if self.calls == 1:
                return Verification(status=VerificationStatus.NOT_VERIFIED, reason="not yet")
            self.started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return Verification(status=VerificationStatus.NOT_VERIFIED, reason="late")

    broker = InputBroker()
    verifier = SlowSecondVerifier()
    tool = FakeToolExecutor(ToolResult(success=True, message="sent"))
    perception = SequencePerception(
        SceneSnapshot(active_window={"title": "Home"}),
        SceneSnapshot(active_window={"title": "Still home"}),
    )
    executor = MissionExecutor(
        planner=StaticPlanner(plan_for_title("Done")), perception=perception,
        tool_executor=tool, registry=build_registry(), input_broker=broker,
        verifier=verifier,
    )
    task = asyncio.create_task(executor.run("set demo"))
    await asyncio.wait_for(verifier.started.wait(), timeout=0.5)
    broker.stop()
    outcome = await asyncio.wait_for(task, timeout=0.5)

    assert outcome.status is TaskStatus.INTERRUPTED
    assert len(tool.calls) == 1
    assert verifier.cancelled is True


@pytest.mark.asyncio
async def test_external_mission_cancellation_cancels_inflight_action() -> None:
    import asyncio
    from uni.operator.input_broker import InputBroker

    broker = InputBroker()
    tool = SlowToolExecutor()
    executor = MissionExecutor(
        planner=StaticPlanner(plan_for_title('Done')),
        perception=SequencePerception(SceneSnapshot()),
        tool_executor=tool,
        registry=build_registry(physical=False),
        input_broker=broker,
    )

    task = asyncio.create_task(executor.run('set demo'))
    await asyncio.wait_for(tool.started.wait(), timeout=0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert tool.cancelled is True
