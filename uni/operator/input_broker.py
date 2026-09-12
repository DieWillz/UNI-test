from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from uuid import uuid4


class InputStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class InputLease:
    owner: str
    token: str
    generation: int


class InputBroker:
    """Single owner for OS mouse/keyboard actions.

    STOP is latched and invalidates an already-issued lease by generation.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._generation = 0
        self._stopped = False
        self._stop_event = asyncio.Event()
        self._owner: str | None = None

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def owner(self) -> str | None:
        return self._owner

    @property
    def generation(self) -> int:
        return self._generation

    def ensure_active(self, generation: int) -> None:
        if self._stopped or generation != self._generation:
            raise InputStopped("STOP_REQUESTED: mission generation invalidated")

    def stop(self) -> None:
        self._stopped = True
        self._stop_event.set()
        self._generation += 1

    def reset_stop(self) -> None:
        self._stopped = False
        self._stop_event.clear()
        self._generation += 1

    async def wait_stopped(self) -> None:
        await self._stop_event.wait()

    def check(self, lease: InputLease) -> None:
        if self._stopped or lease.generation != self._generation:
            raise InputStopped("physical_input_stopped")
        if self._owner != lease.owner:
            raise InputStopped("physical_input_lease_lost")

    @asynccontextmanager
    async def acquire(self, owner: str, *, timeout: float = 15.0):
        if self._stopped:
            raise InputStopped("physical_input_stopped")
        lock_task = asyncio.create_task(self._lock.acquire())
        stop_task = asyncio.create_task(self.wait_stopped())
        try:
            done, _ = await asyncio.wait(
                {lock_task, stop_task},
                timeout=max(0.1, timeout),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                if lock_task.done() and not lock_task.cancelled() and lock_task.result():
                    self._lock.release()
                else:
                    lock_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await lock_task
                raise InputStopped("physical_input_stopped")
            if lock_task not in done:
                lock_task.cancel()
                with suppress(asyncio.CancelledError):
                    await lock_task
                raise TimeoutError("physical_input_busy")
        except BaseException:
            # Caller cancellation must not leave the internal acquire task queued.
            # If it already won the race, release the orphaned lock immediately.
            if lock_task.done():
                if not lock_task.cancelled():
                    with suppress(Exception):
                        if lock_task.result() and self._lock.locked():
                            self._lock.release()
            else:
                lock_task.cancel()
                with suppress(asyncio.CancelledError):
                    await lock_task
            raise
        finally:
            if not stop_task.done():
                stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task

        lease = InputLease(owner=owner, token=uuid4().hex, generation=self._generation)
        self._owner = owner
        try:
            self.check(lease)
            yield lease
        finally:
            if self._owner == owner:
                self._owner = None
            self._lock.release()
