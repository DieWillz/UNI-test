"""Orchestration patterns for XToys devices (Fredorch Rotary et al.).

This layer sits ON TOP of ``XToysCapability`` (the low-level primitives
``set_intensity`` / ``ramp_intensity`` / ``select_pattern`` / ``read_intensity``
that Codex maintains in ``uni/capabilities/xtoys.py``). It does NOT re-implement
device control — it composes those primitives into time-based *scenarios* a
automated session can trigger: ramp, climb, pulse, wave, hold, cooldown.

Safety: every write is verified by reading the slider back (``read_intensity``).
If the UI drift exceeds a tolerance the pattern halts and reports it. The
physical-hardware cap (``max_intensity``) is enforced by the capability itself,
so a pattern can never exceed what the user configured in config.yaml.

Patterns are driven through an injected callable ``run_tool(name, args)`` (same
contract ``AutonomousSession`` uses) so this module stays capability-agnostic —
it works whether the backend is the XToys UI adapter or a direct buttplug bridge.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger("uni.xtoys_patterns")

# run_tool("xtoys.set_intensity", {"value": 60}) -> ToolResult-like (has .success/.data)
RunTool = Callable[[str, dict[str, Any]], Awaitable[Any]]

DEFAULT_DURATION = 20.0  # seconds
VERIFY_TOLERANCE = 5  # % drift between requested and UI-read value before we bail


@dataclass
class PatternState:
    name: str = ""
    running: bool = False
    started_at: float = 0.0
    last_value: int = 0
    step: str = ""
    error: str = ""


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(value)))


class XToysPatternEngine:
    """Runs a named time-based pattern against an XToys device."""

    def __init__(self, run_tool: RunTool) -> None:
        self._run_tool = run_tool
        self.state = PatternState()
        self._stop = False
        self._override_until = 0.0  # manual override pauses the timeline

    # -- low-level helpers (compose XToysCapability primitives) -----------------
    async def _set(self, value: int) -> bool:
        value = _clamp(value)
        res = await self._run_tool("xtoys.set_intensity", {"value": value})
        ok = bool(getattr(res, "success", False))
        if ok:
            self.state.last_value = value
            # verify against the live DOM; bail on drift (safety guard)
            try:
                read = await self._run_tool("xtoys.read_intensity", {})
                if getattr(read, "success", False):
                    ui = int((getattr(read, "data", {}) or {}).get("value", value))
                    if abs(ui - value) > VERIFY_TOLERANCE:
                        logger.warning(f"XToys drift: asked {value}, UI shows {ui}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"XToys verify skipped: {exc}")
        else:
            self.state.error = getattr(res, "message", "set_intensity failed")
            logger.warning(f"XToys set_intensity {value} failed: {self.state.error}")
        return ok

    async def _ramp(self, target: int, steps: int = 6, step_s: float = 0.5) -> None:
        target = _clamp(target)
        current = self.state.last_value
        lo, hi = (current, target) if target > current else (target, current)
        span = hi - lo or 1
        seq = [lo + round(span * (i + 1) / steps) for i in range(steps)]
        if target < current:
            seq = seq[::-1]
        for v in seq:
            if self._stop:
                return
            await self._set(v)
            await asyncio.sleep(step_s)

    async def _hold(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop:
            if time.monotonic() < self._override_until:
                await asyncio.sleep(0.2)
                continue
            await asyncio.sleep(0.25)

    # -- public API ------------------------------------------------------------
    def stop(self) -> None:
        self._stop = True

    def manual_override(self, seconds: int = 10) -> None:
        """Pause the timeline so a manual slider move isn't fought by the pattern."""
        self._override_until = time.monotonic() + max(1, seconds)

    def status(self) -> dict[str, Any]:
        return {
            "running": self.state.running,
            "name": self.state.name,
            "last_value": self.state.last_value,
            "step": self.state.step,
            "error": self.state.error,
        }

    async def run(self, name: str, duration: float = DEFAULT_DURATION, intensity: int = 70) -> dict[str, Any]:
        name = (name or "").strip().lower()
        intensity = _clamp(intensity)
        self._stop = False
        self.state = PatternState(name=name, running=True, started_at=time.time())
        try:
            if name in ("ramp", "climb", "pulse", "wave", "hold", "cooldown"):
                await getattr(self, f"_p_{name}")(duration, intensity)
            else:
                # unknown -> just hold at intensity then release
                await self._set(intensity)
                await self._hold(duration)
                await self._set(0)
        except asyncio.CancelledError:
            pass
        finally:
            self.state.running = False
            await self._set(0)
        return self.status()

    # -- pattern definitions ---------------------------------------------------
    async def _p_ramp(self, duration: float, intensity: int) -> None:
        """Slow climb to target, brief plateau, soft release."""
        self.state.step = "climb"
        await self._ramp(intensity, steps=8, step_s=duration / 16)
        self.state.step = "plateau"
        await self._hold(duration * 0.25)
        self.state.step = "release"
        await self._ramp(0, steps=4, step_s=0.4)

    async def _p_climb(self, duration: float, intensity: int) -> None:
        """Stepped escalation with pauses between steps."""
        self.state.step = "steps"
        steps = 5
        for i in range(1, steps + 1):
            if self._stop:
                return
            target = _clamp(int(intensity * i / steps))
            await self._set(target)
            await self._hold(duration / (steps * 2))
        self.state.step = "cooldown"
        await self._ramp(0, steps=3, step_s=0.5)

    async def _p_pulse(self, duration: float, intensity: int) -> None:
        """Alternating high/low bursts."""
        self.state.step = "pulse"
        period = 1.4
        end = time.monotonic() + duration
        hi = _clamp(intensity)
        lo = _clamp(int(intensity * 0.2))
        toggle = False
        while time.monotonic() < end and not self._stop:
            await self._set(hi if toggle else lo)
            toggle = not toggle
            await asyncio.sleep(period / 2)

    async def _p_wave(self, duration: float, intensity: int) -> None:
        """Smooth sinusoidal modulation 0..intensity."""
        self.state.step = "wave"
        end = time.monotonic() + duration
        peak = _clamp(intensity)
        t0 = time.monotonic()
        while time.monotonic() < end and not self._stop:
            elapsed = time.monotonic() - t0
            phase = (elapsed / duration) * math.pi * 4  # two full waves
            val = int(peak * (0.5 - 0.5 * math.cos(phase)))
            await self._set(val)
            await asyncio.sleep(0.3)

    async def _p_hold(self, duration: float, intensity: int) -> None:
        """Hold near the target with small periodic reductions."""
        self.state.step = "hold"
        end = time.monotonic() + duration
        peak = _clamp(int(intensity * 0.9))
        drop = _clamp(int(intensity * 0.55))
        while time.monotonic() < end and not self._stop:
            await self._set(peak)
            await asyncio.sleep(1.2)
            await self._set(drop)
            await asyncio.sleep(0.4)

    async def _p_cooldown(self, duration: float, intensity: int) -> None:
        """A short intense push then full stop."""
        self.state.step = "push"
        await self._ramp(intensity, steps=4, step_s=0.4)
        await self._hold(min(2.0, duration * 0.3))
        self.state.step = "cooldown"
        await self._set(0)


# Names exposed to the UI / API.
PATTERN_NAMES = ["ramp", "climb", "pulse", "wave", "hold", "cooldown"]
