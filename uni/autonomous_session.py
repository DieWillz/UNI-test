"""Autonomous mistress session: continuous dirty talk + device intensity timeline.

Start: «начни сессию» / «режим госпожи» / «автономный режим»
Stop:  «стоп» / «красный» / «остановись» / «останови сессию»

Device motion is driven through the XToys capability (xtoys.open / get_status /
set_intensity) — i.e. the xtoys.app → Intiface path — never a raw browser socket.
Safety gates (verified_physical / require_connect) are intentionally removed at the
owner's request; the human always holds the physical device remote (hardware kill-switch).
Only hardware-bounded max_intensity and an instant ESC/stop remain.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from rich.console import Console

console = Console()

SpeakFn = Callable[[str], Awaitable[bool]]
ToolFn = Callable[[str, dict[str, Any]], Awaitable[Any]]
ChatFn = Callable[[list[dict[str, Any]]], Awaitable[Any]]
LogFn = Callable[[str, object], None]
InterruptFn = Callable[[], Awaitable[None]]

DEFAULT_CURVES: dict[str, list[tuple[float, int]]] = {
    "tease": [
        (8.0, 15),
        (6.0, 25),
        (5.0, 10),
        (10.0, 35),
        (6.0, 20),
        (4.0, 5),
        (12.0, 40),
        (8.0, 30),
    ],
    "build": [
        (8.0, 30),
        (10.0, 45),
        (8.0, 55),
        (6.0, 35),
        (12.0, 65),
        (8.0, 50),
        (6.0, 70),
        (5.0, 40),
    ],
    "pulse": [
        (3.0, 55),
        (2.0, 15),
        (3.0, 70),
        (2.0, 20),
        (4.0, 80),
        (2.0, 25),
        (3.0, 65),
        (4.0, 10),
    ],
    "peak": [
        (6.0, 75),
        (5.0, 90),
        (4.0, 70),
        (7.0, 95),
        (5.0, 85),
        (8.0, 60),
        (6.0, 100),
        (10.0, 40),
    ],
    "aftercare": [
        (12.0, 25),
        (10.0, 15),
        (12.0, 10),
        (15.0, 5),
        (10.0, 20),
        (15.0, 0),
    ],
}

PHASE_ORDER = ["tease", "build", "pulse", "peak", "aftercare"]

OPERATIONAL_PROMPT = "Ты — властная госпожа в автономной сессии с секс-машинкой."

FALLBACK_LINES = [
    "Терпи. Я сейчас вдавлю тебя этой машинкой глубже.",
    "Слышишь как я трахаю тебя? Ты тупая дырка и я превращу тебя в настоящую девку.",
    "Ещё быстрее. Не смей сжиматься — принимай. Твою пиздёнку надо тренировать",
    "Хорошая шлюшка. Стонешь уже от одних оборотов.",
    "Я прибавляю скорость. Будешь брать всё, что дам.",
    "Слишком быстро? Слишком глубоко? Мне похую шалава!",
]


@dataclass
class SessionState:
    active: bool = False
    phase: str = "tease"
    target_intensity: int = 0
    applied_intensity: int = 0
    last_applied_intensity: int = -1
    curve_index: int = 0
    phase_started_at: float = 0.0
    segment_ends_at: float = 0.0
    monologue_count: int = 0
    started_at: float = 0.0
    last_error: str = ""
    consecutive_errors: int = 0
    device_ready: bool = False
    aftercare_cycles: int = 0
    override_until: float = 0.0
    override_value: int | None = None
    ending: bool = False
    notes: list[str] = field(default_factory=list)


class AutonomousSession:
    """Device timeline + speech monologue with safety, ramp, and auto-end."""

    def __init__(
        self,
        *,
        run_tool: ToolFn,
        speak: SpeakFn,
        chat: ChatFn,
        role_prompt: str = "",
        max_intensity: int = 50,
        monologue_interval: float = 12.0,
        phase_seconds: float = 90.0,
        ramp_step: int = 5,
        session_max_seconds: float = 1800.0,
        override_seconds: float = 45.0,
        require_connect: bool = False,
        interrupt_speech: InterruptFn | None = None,
        log: LogFn | None = None,
    ) -> None:
        self._run_tool = run_tool
        self._speak = speak
        self._chat = chat
        self._role_prompt = role_prompt
        self.max_intensity = max(0, min(100, max_intensity))
        self.monologue_interval = max(4.0, monologue_interval)
        self.phase_seconds = max(20.0, phase_seconds)
        self.ramp_step = max(1, min(20, ramp_step))
        self.session_max_seconds = max(60.0, session_max_seconds)
        self.override_seconds = max(10.0, override_seconds)
        self.require_connect = require_connect
        self._interrupt_speech = interrupt_speech
        self._log = log or (lambda _e, _m: None)
        self.state = SessionState()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._line_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)

    @property
    def active(self) -> bool:
        return self.state.active and self._task is not None and not self._task.done()

    def _clamp(self, value: int) -> int:
        return max(0, min(int(value), self.max_intensity))

    async def _interrupt(self) -> None:
        if self._interrupt_speech is not None:
            try:
                await self._interrupt_speech()
            except Exception:
                pass

    async def start(self, *, open_xtoys: bool = True, confirm_ready: bool = True) -> str:
        async with self._lock:
            if self.active:
                return "Сессия уже идёт. Скажи «стоп», чтобы остановить."
            self._stop_event.clear()
            self.state = SessionState(
                active=True,
                phase="tease",
                started_at=time.monotonic(),
                phase_started_at=time.monotonic(),
            )
            while not self._line_queue.empty():
                try:
                    self._line_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            if open_xtoys:
                opened = await self._run_tool("xtoys.open", {})
                ok = getattr(opened, "success", False)
                msg = getattr(opened, "message", str(opened))
                self._log("SESSION", f"xtoys.open: {msg}")
                if not ok:
                    self.state.active = False
                    return (
                        f"Не удалось открыть XToys: {msg}. "
                        "Открой вкладку вручную и повтори «начни сессию»."
                    )

            status = await self._run_tool("xtoys.get_status", {})
            status_text = ""
            if getattr(status, "success", False) and isinstance(getattr(status, "data", None), dict):
                status_text = str(status.data.get("visible_text") or "").casefold()
            connected_hint = any(
                token in status_text
                for token in ("connected", "подключ", "disconnect", "отключ", "fredorch", "rotary")
            )
            if self.require_connect and not connected_hint:
                self.state.active = False
                return (
                    "XToys открыт, но устройство не видно как подключённое. "
                    "Подключи Fredorch (Connect) и снова скажи «начни сессию»."
                )

            await self._apply_intensity(0, force=True)
            self.state.device_ready = True
            self.state.applied_intensity = 0
            self._arm_segment()
            self._ensure_task()

            intro = (
                "Сессия. Я беру пульт: буду говорить грязно и крутить машинку сама, жёстко. "
            )
            if confirm_ready and not connected_hint:
                intro += "Connect на XToys, если ещё не зелёный. "
            intro += "Физический пульт у тебя — я не жду команд."
            return intro

    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loops(), name="uni-autonomous-session")

    async def stop(self, *, reason: str = "user") -> str:
        await self._interrupt()
        async with self._lock:
            self._stop_event.set()
            self.state.active = False
            self.state.ending = True
            task = self._task
            self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._force_zero()
        self._log("SESSION", f"stopped reason={reason}")
        return "Сессия остановлена. Интенсивность сброшена в ноль."

    async def emergency_stop(self) -> str:
        """Fast path: interrupt speech, cancel loops, zero intensity."""
        await self._interrupt()
        self._stop_event.set()
        self.state.active = False
        self.state.ending = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._force_zero()
        self._log("SESSION", "emergency_stop")
        return "Аварийный стоп. Всё выключено."

    async def _force_zero(self) -> None:
        try:
            await self._run_tool("xtoys.set_intensity", {"value": 0})
        except Exception as exc:
            self._log("SESSION", f"zero failed: {exc}")
        self.state.last_applied_intensity = 0
        self.state.target_intensity = 0
        self.state.applied_intensity = 0
        self.state.override_value = None
        self.state.override_until = 0.0

    def set_manual_override(self, value: int) -> str:
        """Pause timeline and hold a user-requested intensity for override_seconds."""
        if not self.active:
            return ""
        bounded = self._clamp(value)
        self.state.override_value = bounded
        self.state.override_until = time.monotonic() + self.override_seconds
        self._log("SESSION", f"override {bounded}% for {self.override_seconds}s")
        return (
            f"Ок, держу {bounded}% примерно {int(self.override_seconds)} секунд, "
            "потом снова веду сама."
        )

    def _arm_segment(self) -> None:
        curve = DEFAULT_CURVES.get(self.state.phase, DEFAULT_CURVES["tease"])
        idx = self.state.curve_index % len(curve)
        duration, intensity = curve[idx]
        self.state.target_intensity = self._clamp(intensity)
        self.state.segment_ends_at = time.monotonic() + duration
        self.state.curve_index = idx + 1

    def _maybe_advance_phase(self) -> bool:
        """Advance phase. Returns True if session should end after aftercare."""
        elapsed = time.monotonic() - self.state.phase_started_at
        if elapsed < self.phase_seconds:
            return False
        try:
            i = PHASE_ORDER.index(self.state.phase)
        except ValueError:
            i = 0
        if self.state.phase == "aftercare":
            self.state.aftercare_cycles += 1
            if self.state.aftercare_cycles >= 1:
                return True
            self.state.phase_started_at = time.monotonic()
            self.state.curve_index = 0
            return False
        next_phase = PHASE_ORDER[min(i + 1, len(PHASE_ORDER) - 1)]
        if next_phase != self.state.phase:
            self.state.phase = next_phase
            self.state.phase_started_at = time.monotonic()
            self.state.curve_index = 0
            self._log("SESSION", f"phase → {next_phase}")
        return False

    async def _apply_intensity(self, value: int, *, force: bool = False) -> None:
        target = self._clamp(value)
        if not force and target == self.state.last_applied_intensity:
            return
        if self.state.consecutive_errors >= 5 and not force:
            if self.state.consecutive_errors == 5:
                self._log("DEVICE", "backoff after repeated failures")
            await asyncio.sleep(2.0)
            if self.state.consecutive_errors >= 8:
                return

        result = await self._run_tool("xtoys.set_intensity", {"value": target})
        ok = getattr(result, "success", False)
        msg = getattr(result, "message", str(result))
        if ok:
            self.state.last_applied_intensity = target
            self.state.applied_intensity = target
            self.state.last_error = ""
            self.state.consecutive_errors = 0
            console.print(f"[magenta]DEVICE → {target}%[/magenta]")
        else:
            self.state.last_error = msg
            self.state.consecutive_errors += 1
            console.print(f"[red]DEVICE fail {target}%: {msg}[/red]")
        self._log("DEVICE", f"{target}% ok={ok} {msg}")

    async def _ramp_toward(self, desired: int) -> None:
        desired = self._clamp(desired)
        current = self.state.applied_intensity
        if current == desired:
            await self._apply_intensity(desired)
            return
        step = self.ramp_step if desired > current else -self.ramp_step
        nxt = current + step
        if (step > 0 and nxt > desired) or (step < 0 and nxt < desired):
            nxt = desired
        await self._apply_intensity(nxt)

    def _effective_target(self) -> int:
        now = time.monotonic()
        if self.state.override_value is not None and now < self.state.override_until:
            return self._clamp(self.state.override_value)
        if self.state.override_value is not None and now >= self.state.override_until:
            self.state.override_value = None
            self._log("SESSION", "override expired")
        return self.state.target_intensity

    async def _device_loop(self) -> None:
        while not self._stop_event.is_set() and self.state.active:
            now = time.monotonic()
            if now - self.state.started_at >= self.session_max_seconds:
                self._log("SESSION", "max duration reached")
                self.state.ending = True
                break
            if now >= self.state.segment_ends_at:
                if self._maybe_advance_phase():
                    self.state.ending = True
                    break
                self._arm_segment()
            await self._ramp_toward(self._effective_target())
            await asyncio.sleep(0.4)

    async def _generate_line(self) -> str:
        intensity = self.state.applied_intensity
        phase = self.state.phase
        system = (
            OPERATIONAL_PROMPT
            + f"\nФаза: {phase}. Интенсивность сейчас: {intensity}% (макс {self.max_intensity}%)."
        )
        try:
            response = await asyncio.wait_for(
                self._chat(
                    [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": f"Реплика #{self.state.monologue_count + 1}. Только текст.",
                        },
                    ]
                ),
                timeout=8.0,
            )
            text = (getattr(response, "text", None) or "").strip()
            if getattr(response, "error", None) or not text:
                return random.choice(FALLBACK_LINES)
            text = " ".join(text.split())
            if len(text) > 180:
                cut = text[:181]
                boundary = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
                text = cut[: boundary + 1] if boundary >= 30 else cut.rstrip() + "…"
            return text
        except Exception:
            return random.choice(FALLBACK_LINES)

    async def _prefetch_loop(self) -> None:
        await asyncio.sleep(0.5)
        while not self._stop_event.is_set() and self.state.active:
            if self._line_queue.full():
                await asyncio.sleep(0.4)
                continue
            line = await self._generate_line()
            if self._stop_event.is_set() or not self.state.active:
                break
            try:
                self._line_queue.put_nowait(line)
            except asyncio.QueueFull:
                await asyncio.sleep(0.2)

    async def _speech_loop(self) -> None:
        await asyncio.sleep(1.5)
        while not self._stop_event.is_set() and self.state.active:
            try:
                line = await asyncio.wait_for(self._line_queue.get(), timeout=10.0)
            except asyncio.TimeoutError:
                line = random.choice(FALLBACK_LINES)
            if self._stop_event.is_set() or not self.state.active:
                break
            self.state.monologue_count += 1
            console.print(f"[yellow]MONOLOGUE:[/yellow] {line}")
            self._log("MONOLOGUE", line)
            await self._speak(line)
            wait = max(5.0, self.monologue_interval + random.uniform(-2.0, 3.0))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                continue

    async def _run_loops(self) -> None:
        console.print("[bold magenta]Autonomous session RUNNING[/bold magenta]")
        try:
            await asyncio.gather(
                self._device_loop(),
                self._speech_loop(),
                self._prefetch_loop(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            was_ending = self.state.ending
            self.state.active = False
            await self._force_zero()
            console.print("[bold magenta]Autonomous session STOPPED[/bold magenta]")
            if was_ending and not self._stop_event.is_set():
                try:
                    await self._speak("Хватит на этот круг. Можешь включить снова — я не наспрашивалась.")
                except Exception:
                    pass
            self._stop_event.set()

    def status_text(self) -> str:
        if not self.active:
            return "Автономная сессия выключена."
        elapsed = int(time.monotonic() - self.state.started_at)
        ov = ""
        if self.state.override_value is not None and time.monotonic() < self.state.override_until:
            left = int(self.state.override_until - time.monotonic())
            ov = f" override {self.state.override_value}% ещё {left}с;"
        return (
            f"Сессия {elapsed}с, фаза «{self.state.phase}», "
            f"цель {self.state.target_intensity}%, сейчас {self.state.applied_intensity}%, "
            f"реплик {self.state.monologue_count}.{ov}"
            + (f" Ошибка: {self.state.last_error}" if self.state.last_error else "")
        )
