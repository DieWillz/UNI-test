from __future__ import annotations

import asyncio

import pytest

from uni.operator.input_broker import InputBroker, InputStopped


@pytest.mark.asyncio
async def test_only_one_owner_holds_physical_input() -> None:
    broker = InputBroker()
    order: list[str] = []

    async def worker(name: str, hold: float) -> None:
        async with broker.acquire(name) as lease:
            broker.check(lease)
            order.append(f"{name}:in")
            await asyncio.sleep(hold)
            order.append(f"{name}:out")

    first = asyncio.create_task(worker("one", 0.03))
    await asyncio.sleep(0.005)
    second = asyncio.create_task(worker("two", 0.0))
    await asyncio.gather(first, second)
    assert order == ["one:in", "one:out", "two:in", "two:out"]


@pytest.mark.asyncio
async def test_stop_invalidates_current_lease_and_latches_new_input() -> None:
    broker = InputBroker()
    async with broker.acquire("mission") as lease:
        broker.stop()
        with pytest.raises(InputStopped):
            broker.check(lease)
    with pytest.raises(InputStopped):
        async with broker.acquire("next"):
            pass
    broker.reset_stop()
    async with broker.acquire("next") as lease:
        broker.check(lease)


@pytest.mark.asyncio
async def test_waiting_acquire_is_interrupted_by_stop() -> None:
    broker = InputBroker()
    entered = asyncio.Event()

    async def holder() -> None:
        async with broker.acquire("holder"):
            entered.set()
            await asyncio.sleep(1.0)

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    waiter = asyncio.create_task(broker.acquire("waiter").__aenter__())
    await asyncio.sleep(0.01)
    broker.stop()

    with pytest.raises(InputStopped):
        await asyncio.wait_for(waiter, timeout=0.2)

    holder_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder_task

@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leak_input_lock() -> None:
    broker = InputBroker()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with broker.acquire('holder'):
            entered.set()
            await release.wait()

    holder_task = asyncio.create_task(holder())
    await entered.wait()

    waiter_cm = broker.acquire('cancelled-waiter')
    waiter = asyncio.create_task(waiter_cm.__aenter__())
    await asyncio.sleep(0.01)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release.set()
    await holder_task

    async with asyncio.timeout(0.2):
        async with broker.acquire('next') as lease:
            broker.check(lease)
