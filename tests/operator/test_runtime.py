from __future__ import annotations

import asyncio
from types import SimpleNamespace

from uni.operator.runtime import OperatorRuntime


class FakeSession:
    pass


class FakeComputer:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("not used during construction")


class FakeVision:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("not used during construction")


def test_runtime_builds_one_coherent_operator_stack() -> None:
    runtime = OperatorRuntime(
        brain=SimpleNamespace(),
        browser_session=FakeSession(),
        computer=FakeComputer(),
        vision=FakeVision(),
        tool_executor=SimpleNamespace(),
    )

    assert runtime.executor.input_broker is runtime.input_broker
    assert runtime.executor.perception is runtime.perception
    assert runtime.executor.browser_provider is runtime.browser
    assert runtime.executor.windows_provider is runtime.windows
    assert runtime.executor.file_provider is runtime.files


def test_stop_and_resume_use_the_same_input_broker() -> None:
    runtime = OperatorRuntime(
        brain=SimpleNamespace(), browser_session=FakeSession(), computer=FakeComputer(),
        vision=FakeVision(), tool_executor=SimpleNamespace(),
    )
    runtime.stop()
    assert runtime.input_broker.stopped is True
    runtime.resume()
    assert runtime.input_broker.stopped is False


async def _run_after_stop(runtime: OperatorRuntime) -> bool:
    class FakeExecutor:
        async def run(self, _goal, *, permissions=None):
            return runtime.input_broker.stopped

    runtime.executor = FakeExecutor()
    runtime.stop()
    return await runtime.run("open calculator")


def test_new_mission_resumes_input_only_when_it_starts() -> None:
    import asyncio

    runtime = OperatorRuntime(
        brain=SimpleNamespace(), browser_session=FakeSession(), computer=FakeComputer(),
        vision=FakeVision(), tool_executor=SimpleNamespace(),
    )

    was_stopped_when_executor_started = asyncio.run(_run_after_stop(runtime))
    assert was_stopped_when_executor_started is False


async def _verify_stop_stays_latched_while_old_mission_holds_lock(runtime: OperatorRuntime) -> tuple[bool, bool]:
    started = asyncio.Event()
    release = asyncio.Event()
    observed: list[bool] = []

    class BlockingExecutor:
        async def run(self, goal, *, permissions=None):
            if goal == "old mission":
                started.set()
                await release.wait()
            else:
                observed.append(runtime.input_broker.stopped)
            return goal

    runtime.executor = BlockingExecutor()
    old_task = asyncio.create_task(runtime.run("old mission"))
    await started.wait()
    runtime.stop()
    new_task = asyncio.create_task(runtime.run("new mission"))
    await asyncio.sleep(0)
    latched_while_old_running = runtime.input_broker.stopped
    release.set()
    await asyncio.gather(old_task, new_task)
    return latched_while_old_running, observed[0]


def test_stop_is_not_cleared_until_previous_mission_releases_lock() -> None:
    runtime = OperatorRuntime(
        brain=SimpleNamespace(), browser_session=FakeSession(), computer=FakeComputer(),
        vision=FakeVision(), tool_executor=SimpleNamespace(),
    )

    latched_during_old, stopped_when_new_started = asyncio.run(
        _verify_stop_stays_latched_while_old_mission_holds_lock(runtime)
    )
    assert latched_during_old is True
    assert stopped_when_new_started is False


async def _attempt_resume_during_active_mission(runtime: OperatorRuntime) -> tuple[bool, bool]:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingExecutor:
        async def run(self, _goal, *, permissions=None):
            started.set()
            await release.wait()
            return "done"

    runtime.executor = BlockingExecutor()
    task = asyncio.create_task(runtime.run("active mission"))
    await started.wait()
    runtime.stop()
    resumed = runtime.resume()
    still_stopped = runtime.input_broker.stopped
    release.set()
    await task
    return resumed, still_stopped


def test_resume_cannot_clear_stop_while_mission_is_active() -> None:
    runtime = OperatorRuntime(
        brain=SimpleNamespace(), browser_session=FakeSession(), computer=FakeComputer(),
        vision=FakeVision(), tool_executor=SimpleNamespace(),
    )
    resumed, still_stopped = asyncio.run(_attempt_resume_during_active_mission(runtime))
    assert resumed is False
    assert still_stopped is True


async def _queue_before_stop(runtime: OperatorRuntime) -> tuple[bool, list[str]]:
    started = asyncio.Event()
    release = asyncio.Event()
    executed: list[str] = []

    class BlockingExecutor:
        async def run(self, goal, *, permissions=None):
            executed.append(goal)
            if goal == "old mission":
                started.set()
                await release.wait()
            return goal

    runtime.executor = BlockingExecutor()
    old_task = asyncio.create_task(runtime.run("old mission"))
    await started.wait()
    queued_task = asyncio.create_task(runtime.run("queued before stop"))
    await asyncio.sleep(0)
    runtime.stop()
    release.set()
    await old_task
    try:
        await asyncio.wait_for(queued_task, timeout=0.1)
    except asyncio.TimeoutError:
        queued_task.cancel()
        await asyncio.gather(queued_task, return_exceptions=True)
    return runtime.input_broker.stopped, executed


def test_mission_queued_before_stop_cannot_auto_resume_after_emergency_stop() -> None:
    runtime = OperatorRuntime(
        brain=SimpleNamespace(), browser_session=FakeSession(), computer=FakeComputer(),
        vision=FakeVision(), tool_executor=SimpleNamespace(),
    )
    stopped, executed = asyncio.run(_queue_before_stop(runtime))
    assert stopped is True

