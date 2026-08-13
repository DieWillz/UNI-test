from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import threading
import time

from rich.console import Console

from uni.config import Config
from uni.contracts import ToolResult
from uni.session_state import SessionState

console = Console()
logger = logging.getLogger(__name__)


class AutonomousController:
    """Hands-free mode: UNI watches the screen, talks and drives XToys on its own.

    Three concurrent loops share one SessionState:
      * VisionObserver  — periodic screenshot -> VLM -> SessionState.screen_desc
      * SpeechDirector  — continuous role-driven phrases via TTS (cancels prior TTS)
      * DeviceController— ramps/verifies XToys intensity, reacts to screen state
    A rare LLM "Conductor" step (every `conductor_interval`) gently steers behavior
    so we don't hammer the (slow) local model on every action.

    SAFETY: device motion is bounded by capabilities.xtoys.max_intensity and only
    starts after an explicit opt-in (capabilities.xtoys.autonomous_physical). ESC or
    the stop-word drops intensity to 0 immediately.
    """

    def __init__(self, agent, config: Config, max_steps: int = 0):
        self.agent = agent
        self.config = config
        self.max_steps = max(0, int(max_steps))  # 0 = без лимита
        self._conductor_cycles = 0
        self.state = SessionState()
        self.acfg = config.autonomous
        # Device motion requires TWO explicit acknowledgments: autonomous.enabled
        # AND capabilities.xtoys.autonomous_physical. By default both are False.
        self.device_allowed = bool(
            config.autonomous.enabled and config.capabilities.xtoys.autonomous_physical
        )
        self._tasks: set[asyncio.Task[None]] = set()
        self._manual_until = 0.0  # timestamp until which manual override halts auto timeline
        self._error_until = 0.0  # backoff: pause device writes after a burst of errors
        self._error_count = 0
        self._conductor_until = 0.0  # prefetch deadline
        self._monologue_queue: list[str] = []
        self._running = False  # autonomous background loop active flag
    # -- safety: instant stop (synchronous-ish, no queue) ---------------------
    def emergency_stop(self) -> None:
        """Immediately drop device to zero and silence speech. Not routed via tasks."""
        self.state.request_stop()
        xtoys = self.agent.capabilities.get("xtoys")
        if xtoys is not None and self.device_allowed:
            try:
                asyncio.create_task(self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 2}))
            except Exception:
                pass
        speech = self.agent.capabilities.get("speech")
        if speech is not None and hasattr(speech, "stop_speaking"):
            try:
                speech.stop_speaking()
            except Exception:
                pass

    def request_manual_override(self, seconds: float = 45.0) -> None:
        """A manual `intensity N` pauses the auto timeline briefly and adopts the value."""
        self._manual_until = asyncio.get_event_loop().time() + float(seconds)
        self.state.intensity = self.state.intensity  # unchanged; timeline will re-adopt later

    # -- helpers ---------------------------------------------------------------
    async def _run_tool(self, name: str, args: dict) -> ToolResult:
        """Execute a tool WITHOUT the global EventLoop lock (parallel autonomy)."""
        return await self.agent.tool_executor.execute(name, args)

    async def _speak(self, text: str) -> None:
        speech = self.agent.capabilities.get("speech")
        if speech is not None:
            await speech.speak(text)
        self.state.last_phrase = text
        self.state.phrase_count += 1

    # -- vision -----------------------------------------------------------------
    async def _vision_loop(self) -> None:
        vision = self.agent.capabilities.get("vision")
        interval = self.acfg.vision_interval_seconds
        while not self.state.stopped:
            try:
                if vision is not None and self.config.capabilities.vision.enabled:
                    result = await self._run_tool(
                        "vision.analyze_screen",
                        {"prompt": "Кратко опиши, что сейчас на экране XToys и вкладке браузера."},
                    )
                    if result.success and isinstance(result.data, dict):
                        self.state.screen_desc = result.data.get("analysis", "")[:500]
                        self.state.screen_updated_at = asyncio.get_event_loop().time()
            except Exception as exc:  # vision is best-effort
                logger.warning("Autonomous vision step failed: %s", exc)
            await asyncio.sleep(interval)

    # -- speech -----------------------------------------------------------------
    async def _speech_loop(self) -> None:
        while not self.state.stopped:
            try:
                phrase = await self._next_phrase_async()
                console.print(f"[magenta]ГОСПОЖА:[/magenta] {phrase}")
                # Push to WebUI (browser plays audio + shows text in the right chat)
                await self._emit_phrase(phrase)
                # Also speak locally if a TTS device is available (best effort)
                await self._speak(phrase)
            except Exception as exc:
                logger.warning("Autonomous speech step failed: %s", exc)
            await asyncio.sleep(self.acfg.speech_interval_seconds)

    async def _emit_phrase(self, text: str) -> None:
        """Push a phrase (+ synthesized audio when available) to the WebUI bridge."""
        if self.state.ui_events is None:
            return
        audio_url = None
        speech = self.agent.capabilities.get("speech")
        if speech is not None and hasattr(speech, "synthesize_to_wav"):
            try:
                wav = await speech.synthesize_to_wav(text)
                if wav is not None:
                    audio_url = f"/api/autonomous/audio/{wav.name}"
            except Exception as exc:  # TTS optional — text still goes to UI
                logger.warning("Autonomous TTS failed (text-only fallback): %s", exc)
        try:
            await self.state.ui_events.put(
                {"type": "phrase", "text": text, "audio_url": audio_url}
            )
        except Exception:
            pass


    async def _next_phrase_async(self) -> str:
        """Use prefetched LLM line if present, else fallback pool (no blocking wait)."""
        if self._monologue_queue:
            return self._monologue_queue.pop(0)
        return self._next_phrase()


    def _next_phrase(self) -> str:
        """Deterministic, role-flavored phrase driven by current device state."""
        intensity = self.state.intensity
        pool = [
            "Ты моя маленькая игрушка. Чувствуй, как я тобой управляю.",
            "Не смей прерываться. Я сама решаю, когда тебе кончать.",
            "Слышишь этот звук? Это я кручу твою машинку.",
            "Хороший мальчик. Сегодня ты мой на все сто процентов.",
            "Я вижу экран, я вижу тебя. Ты под моим контролем.",
            "Тише. Просто чувствуй и выполняй. Я всё вижу.",
            "Сучий ты мой. Рот закрой и крутись для меня.",
            "Я сама выбираю, как сильно тебя гнать. Ты только дыши.",
            "Хочешь сильнее? Попроси как следует. Нет — я сама решу.",
        ]
        if intensity >= 60:
            pool += ["Гони на полную, моя шлюшка. Я не остановлюсь.",
                     "Вот так, быстрее, глубже — ты же хотел, чтобы я сама?",
                     "Почти на пределе. Держись, я не жалею."]
        elif intensity == 0:
            pool += ["Пока стоишь. Но это ненадолго, моя собственность."]
        else:
            pool += ["Чуть-чуть прибавим, ты же любишь послушание.",
                     "Темп выбираю я. Расслабься и получай.",
                     "Медленно разгоняю твою машинку. Чувствуй каждый оборот."]
        return random.choice(pool)

    # -- device -----------------------------------------------------------------
    async def _device_loop(self) -> None:
        interval = self.acfg.device_interval_seconds
        while not self.state.stopped:
            try:
                if self.device_allowed:
                    await self._drive_device()
            except Exception as exc:
                logger.warning("Autonomous device step failed: %s", exc)
            await asyncio.sleep(interval)

    async def _drive_device(self) -> None:
        xtoys = self.agent.capabilities.get("xtoys")
        if xtoys is None:
            return
        # safety: any stop signal -> intensity 0
        if self.state.stopped:
            await self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 3})
            self.state.intensity = 0
            return
        now = asyncio.get_event_loop().time()
        # error backoff: pause writes after a burst of UI errors
        if now < self._error_until:
            return
        # require_connect: do not move until XToys shows it is connected
        if getattr(self.acfg, "require_connect", False):
            status = await self._run_tool("xtoys.get_status", {})
            if status.success and not self._is_connected(status):
                return
        # aftercare auto-end: finish the session after enough aftercare cycles
        if self.state.phase == "aftercare" and self.state.phase_cycles >= 2:
            console.print("[bold cyan]Сессия завершена. Интенсивность 0.[/bold cyan]")
            await self._speak("Сессия закончена, мой хороший. Можешь выдохнуть.")
            await self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 2})
            self.state.intensity = 0
            self.state.request_stop()
            return
        # manual override pauses the auto timeline, keeps the user-set value
        if now < self._manual_until:
            return
        current = self.state.intensity
        target = self._next_target(current)
        target = max(0, min(self.config.capabilities.xtoys.max_intensity, target))
        if target != current:
            res = await self._run_tool("xtoys.ramp_intensity", {"value": target, "steps": 5})
            if res.success:
                self.state.intensity = target
                self._error_count = 0
            else:
                self._error_count += 1
                logger.warning("XToys ramp failed: %s", res.message)
                if self._error_count >= 3:
                    self._error_until = now + 8.0  # brief backoff
                    self._error_count = 0

    @staticmethod
    def _is_connected(status: ToolResult) -> bool:
        text = ""
        if isinstance(status.data, dict):
            text = status.data.get("visible_text", "") or status.data.get("url", "")
        return bool(re_search(r"connected|disconnect|stop|включ|подключ", text, re.I))

    def _next_target(self, current: int) -> int:
        """Aggressive but clamped random walk that always keeps the toy moving."""
        cap = self.config.capabilities.xtoys.max_intensity
        delta = random.choice([-15, -10, -5, 0, 5, 10, 15])
        target = current + delta
        if target < 5:
            target = random.randint(10, 30)
        if target > cap:
            target = cap - random.randint(0, 10)
        # occasional hard spike for "жёстко"
        if random.random() < 0.15:
            target = max(target, int(cap * 0.85))
        return max(0, min(cap, target))

    # -- conductor (rare LLM steering + prefetch) ------------------------------
    async def _conductor_loop(self) -> None:
        if not self.config.capabilities.vision.enabled:
            return
        while not self.state.stopped:
            try:
                await asyncio.sleep(self.acfg.conductor_interval_seconds)
                if self.state.stopped:
                    break
                # 🤖 B4: мягкий лимит циклов Conductor (0 = без лимита)
                if self.max_steps > 0:
                    self._conductor_cycles += 1
                    if self._conductor_cycles >= self.max_steps:
                        self.state.request_stop()
                        break
                prompt = (
                    "Ты Госпожа, управляешь секс-машинкой через XToys без команд пользователя. "
                    f"Сейчас интенсивность {self.state.intensity}%, экран: {self.state.screen_desc[:300]}. "
                    "Реши, куда сместить интенсивность (число 0..100) и скажи КОРОТКУЮ пошлую фразу (1 предложение). "
                    "Ответь СТРОГО JSON: {\"intensity\": число, \"phrase\": \"...\"}. Никакого другого текста."
                )
                try:
                    response = await asyncio.wait_for(self.agent.brain.simple_chat(prompt), timeout=8.0)
                except Exception:
                    response = ""
                try:
                    import json
                    data = json.loads(response)
                    want = int(data.get("intensity", self.state.intensity))
                    cap = self.config.capabilities.xtoys.max_intensity
                    self.state.intensity = max(0, min(cap, want))
                    phrase = str(data.get("phrase", "")).strip()
                    if phrase:
                        self._monologue_queue.append(phrase)
                except (ValueError, json.JSONDecodeError, TypeError):
                    pass
            except Exception as exc:
                logger.warning("Autonomous conductor step failed: %s", exc)

    # -- lifecycle ---------------------------------------------------------------
    def start(self) -> None:
        """Start the autonomous mode in a dedicated background thread with its own
        asyncio event loop. Safe to call from a sync HTTP handler. Idempotent."""
        if self._running:
            return
        # UI bridge: create the event queue so phrases reach the WebUI.
        if self.state.ui_events is None:
            self.state.ui_events = asyncio.Queue()
        self._running = True
        self._stop_ev = threading.Event()
        self._bg_thread = threading.Thread(target=self._bg_run, name="uni.autonomous", daemon=True)
        self._bg_thread.start()

    def _bg_run(self) -> None:
        """Entry point for the background thread: own asyncio loop, kept alive."""
        try:
            asyncio.run(self._bg_loop())
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"autonomous background loop died: {exc}")
        finally:
            self._running = False

    async def _bg_loop(self) -> None:
        # Fresh stop event bound to this loop.
        self.state.stopped_event = asyncio.Event()
        # First, ensure XToys page is open — only when device motion is allowed.
        # Voice-only mode (autonomous_physical=False) must NOT touch XToys.
        xtoys = self.agent.capabilities.get("xtoys")
        if self.device_allowed and xtoys is not None:
            try:
                await self._run_tool("xtoys.open", {})
            except Exception as exc:
                logger.warning(f"xtoys.open skipped: {exc}")
            await self._run_tool("xtoys.set_verified_physical", {"verified": True})
            await self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 3})
        self._tasks.add(asyncio.create_task(self._vision_loop(), name="uni.vision"))
        self._tasks.add(asyncio.create_task(self._speech_loop(), name="uni.speech"))
        self._tasks.add(asyncio.create_task(self._device_loop(), name="uni.device"))
        self._tasks.add(asyncio.create_task(self._conductor_loop(), name="uni.conductor"))
        self._tasks.add(asyncio.create_task(self._input_watcher(), name="uni.input"))
        # Keep the loop alive until stop is requested.
        await self.state.stopped_event.wait()
        # Cleanup: drop device to zero (if allowed) then cancel all loops.
        if self.device_allowed:
            xtoys = self.agent.capabilities.get("xtoys")
            if xtoys is not None:
                try:
                    await self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 2})
                except Exception:
                    pass
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _input_watcher(self) -> None:
        """Best-effort stop channel: text 'стоп'/'красный' or Ctrl-C/ESC."""
        loop = asyncio.get_running_loop()
        stopped = threading.Event()

        def stdin_reader() -> None:
            try:
                import msvcrt  # Windows only
                while not stopped.is_set():
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ord(ch) in (27,) or ch in ("\x03",):  # ESC / Ctrl-C
                            loop.call_soon_threadsafe(self.state.request_stop)
                            return
                    time.sleep(0.05)
            except (ImportError, Exception):
                pass

        if os.name == "nt":
            threading.Thread(target=stdin_reader, name="uni-stop-key", daemon=True).start()

        try:
            while not self.state.stopped:
                await asyncio.sleep(0.5)
        finally:
            stopped.set()

    async def run(self) -> None:
        await self._bg_loop()

    async def stop(self) -> None:
        self.state.request_stop()
        self._running = False
        # emergency: drop device to zero (best-effort, only if allowed)
        xtoys = self.agent.capabilities.get("xtoys")
        if xtoys is not None and self.device_allowed:
            try:
                await self._run_tool("xtoys.ramp_intensity", {"value": 0, "steps": 2})
            except Exception:
                pass
        self._tasks.clear()
