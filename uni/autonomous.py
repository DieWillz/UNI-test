from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import threading
import time

from rich.console import Console

from uni.config import Config
from uni.contracts import ToolResult
from uni.control_queue import QueueOperation, list_patterns
from uni.session_state import SessionState
from uni.xtoys_control_coordinator import AUTONOMOUS

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

    def __init__(self, agent, config: Config, max_steps: int = 0, control_queue=None):
        self.agent = agent
        self.config = config
        self.max_steps = max(0, int(max_steps))  # 0 = без лимита
        self._conductor_cycles = 0
        self.state = SessionState()
        self.acfg = config.autonomous
        # 🤖 Единый контур: если передана ControlQueue, все действия идут через неё.
        self.control_queue = control_queue
        self._cq_runner_task = None
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
        self._runtime_loop = None
        self.target_intensity = 0
        self.last_error = ""
        self._stop_generation = -1
        if self.control_queue is not None and hasattr(self.control_queue, "set_execution_callback"):
            self.control_queue.set_execution_callback(self._on_queue_execution_event)

    @property
    def coordinator(self):
        return getattr(self.agent, "toy_coordinator", None)

    def _motion_allowed(self) -> bool:
        return bool(self.coordinator and self.config.autonomous.enabled
                    and self.config.capabilities.xtoys.autonomous_physical
                    and self._stop_generation == self.coordinator.stop_generation
                    and self.coordinator.autonomous_allowed())

    async def _set_device(self, value: int) -> bool:
        if self.coordinator is None:
            return False
        if value > 0 and (self.state.stopped or not self._motion_allowed()):
            return False
        return await self.coordinator.set_intensity(AUTONOMOUS, value)

    async def _zero_device(self) -> None:
        if self.coordinator is not None:
            await self.coordinator.release(AUTONOMOUS)
            self.state.intensity = int(round(self.coordinator.current_value))
        self.target_intensity = 0

    def _request_stop(self) -> None:
        loop = self._runtime_loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self.state.request_stop)
        else:
            self.state.request_stop()
    # -- safety: instant stop (synchronous-ish, no queue) ---------------------
    def emergency_stop(self) -> None:
        """Immediately drop device to zero and silence speech. Not routed via tasks."""
        # 🤖 Единый контур: STOP идёт в ControlQueue (увеличивает control_epoch,
        # отменяет очередь, шлёт ноль). Старый путь оставлен как запасной.
        cq = self.control_queue
        if cq is not None:
            loop = getattr(self.agent, "_loop", None)
            try:
                if loop is not None and loop.is_running():
                    asyncio.run_coroutine_threadsafe(cq.apply(__import__("uni.control_queue", fromlist=["QueueOperation"]).QueueOperation(operation="stop")), loop)
                else:
                    # loop недоступен синхронно — ставим защёлку напрямую
                    cq.stopped = True
                    cq.control_epoch += 1
                    cq.mode = "stopped"
            except Exception:
                pass
        self._request_stop()
        coordinator = self.coordinator
        if coordinator is not None:
            coordinator.emergency_stopped = True
            loop = coordinator._loop or self._runtime_loop
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(coordinator.emergency_stop(), loop)
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

    @property
    def state(self):
        """🤖 Единый контур: при наличии ControlQueue состояние берётся из очереди."""
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    def set_manual_override(self, value: int) -> str:
        """🤖 Ручной ползунок во время автономной очереди = передача управления
        владельцу (ТЗ §8). Делегируем в ControlQueue.manual_override."""
        cq = self.control_queue
        if cq is not None:
            try:
                loop = getattr(self.agent, "_loop", None)
                if loop is not None and loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(
                        cq.manual_override(int(value)), loop)
                    fut.result(timeout=5.0)
                else:
                    cq.manual_override(int(value))
            except Exception as exc:
                return f"ручное управление: ошибка {exc}"
            return "Ручной режим: управление передано владельцу."
        # запасной старый путь
        self._manual_until = asyncio.get_event_loop().time() + 45.0
        return "Ручной режим (legacy)."

    # -- helpers ---------------------------------------------------------------
    async def _run_tool(self, name: str, args: dict) -> ToolResult:
        """Execute a tool WITHOUT the global EventLoop lock (parallel autonomy)."""
        return await self.agent.tool_executor.execute(name, args)

    async def _speak(self, text: str) -> None:
        if self.state.stopped:
            return
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
                        "vision.analyze_desktop",
                        {"prompt": "Кратко опиши видимый рабочий стол. Не управляй мышью или браузером."},
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
        if self.state.stopped:
            return
        # The chat consumes text events; speech remains on the existing local path.
        try:
            from uni.webui.server import _publish_runtime_event
            _publish_runtime_event({"type": "assistant_message", "text": text,
                                    "source": "dorch", "ts": time.time()})
        except ImportError:
            pass
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

    async def _plan_control_operation(self, snapshot: dict) -> QueueOperation:
        """Ask the active model for the next short, structured Dorch step."""
        max_intensity = int(snapshot.get("max_intensity", self.config.capabilities.xtoys.max_intensity))
        patterns = ", ".join(list_patterns())
        role_prompt = str(getattr(getattr(self.agent, "role", None), "system_prompt", ""))[:1800]
        prompt = (
            "Ты управляешь Dorch через безопасную серверную очередь Intiface. "
            "Верни ТОЛЬКО JSON без markdown: "
            "{\"operation\":\"append\",\"items\":[{\"type\":\"pattern|hold\","
            "\"pattern_id\":\"...\",\"intensity_percent\":N,\"duration_seconds\":N,"
            "\"speech\":\"короткая реплика\"}],\"reason\":\"...\"}. "
            f"Максимум мощности {max_intensity}%. Доступные паттерны: {patterns}. "
            "Планируй 1 короткий шаг на 3–12 секунд. Реплика должна соответствовать фактически "
            "запрошенному действию и не утверждать физический эффект, которого система не измеряет. "
            f"Текущее состояние очереди: {json.dumps(snapshot, ensure_ascii=False)[:2500]}. "
            f"Активная роль/стиль: {role_prompt}"
        )
        raw = await asyncio.wait_for(self.agent.brain.simple_chat(prompt), timeout=10.0)
        text = str(raw or "").strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S)
        data = json.loads(fenced.group(1) if fenced else text)
        if not isinstance(data, dict):
            raise ValueError("Dorch planner returned non-object JSON")
        operation = str(data.get("operation") or "append").strip().lower()
        if operation not in {"append", "replace_pending", "replace_all"}:
            operation = "append"
        items = data.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Dorch planner returned no items")
        return QueueOperation(
            operation=operation,
            items=[dict(item) for item in items[:3] if isinstance(item, dict)],
            reason=str(data.get("reason") or "autonomous planner")[:300],
        )

    async def handle_control_event(self, event: dict) -> None:
        """Speak only from executor facts, never from an un-applied plan."""
        kind = str(event.get("type") or "")
        if kind == "step_applied":
            text = str(event.get("speech") or "").strip()
            if not text:
                text = f"Intiface принял команду {int(event.get('commanded_value', 0))}%."
        elif kind == "step_failed":
            text = f"Команда устройства не принята: {event.get('message') or 'неизвестная ошибка'}."
        else:
            return
        await self._emit_phrase(text)
        await self._speak(text)

    def _on_queue_execution_event(self, event: dict) -> None:
        try:
            asyncio.get_running_loop().create_task(self.handle_control_event(dict(event)))
            return
        except RuntimeError:
            pass
        loop = self._runtime_loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.handle_control_event(dict(event)), loop)

    async def _control_planner_loop(self) -> None:
        """Keep a short model-authored queue filled while a real device is present."""
        cq = self.control_queue
        if cq is None:
            return
        while not self.state.stopped:
            try:
                coordinator = self.coordinator
                if coordinator is None or not self.device_allowed or coordinator.emergency_stopped:
                    await asyncio.sleep(1.0)
                    continue
                if cq.mode in {"manual", "manual_timed"}:
                    await asyncio.sleep(0.5)
                    continue
                live = coordinator._bridge.status()
                if not live.get("connected"):
                    await coordinator._bridge.connect()
                    live = coordinator._bridge.status()
                if not live.get("connected") or not live.get("devices"):
                    self.last_error = "Intiface подключён, но устройство не найдено" if live.get("connected") else "Intiface не подключён"
                    await asyncio.sleep(2.0)
                    continue
                if cq.stopped:
                    cq.stopped = False
                    cq.mode = "autonomous"
                    cq.session_started_at = time.monotonic()
                snapshot = cq.status()
                if float(snapshot.get("total_remaining_seconds") or 0) < 8.0:
                    op = await self._plan_control_operation(snapshot)
                    result = await cq.apply(op)
                    if not result.get("accepted"):
                        self.last_error = str(result.get("error") or "план Dorch отклонён")
                    else:
                        self.last_error = ""
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"Dorch planner: {exc}"
                logger.warning("Dorch planner step failed: %s", exc)
                await asyncio.sleep(2.0)


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
                if self._motion_allowed():
                    await self._drive_device()
                else:
                    self.last_error = "Движение запрещено: проверьте разрешения, verified_physical и STOP"
                    await self._zero_device()
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("Autonomous device step failed: %s", exc)
                await self._zero_device()
            await asyncio.sleep(interval)

    async def _drive_device(self) -> None:
        coordinator = self.coordinator
        if coordinator is None:
            return
        # safety: any stop signal -> intensity 0
        if self.state.stopped or not self._motion_allowed():
            await self._zero_device()
            return
        now = asyncio.get_event_loop().time()
        # error backoff: pause writes after a burst of UI errors
        if now < self._error_until or now < self._manual_until:
            return
        # Device connection is read from Intiface, never inferred from DOM text.
        status = coordinator._bridge.status()
        if not status.get("connected") or not status.get("devices"):
            self.last_error = "Intiface или устройство не подключены"
            return
        if not await coordinator.acquire(AUTONOMOUS, preempt=True):
            self.last_error = "Источник управления занят или аварийно остановлен"
            return
        # aftercare auto-end: finish the session after enough aftercare cycles
        if self.state.phase == "aftercare" and self.state.phase_cycles >= 2:
            console.print("[bold cyan]Сессия завершена. Интенсивность 0.[/bold cyan]")
            await self._speak("Сессия закончена, мой хороший. Можешь выдохнуть.")
            await self._zero_device()
            self.state.request_stop()
            return
        # manual override pauses the auto timeline, keeps the user-set value
        if now < self._manual_until:
            return
        current = int(round(coordinator.current_value))
        target = self._next_target(current)
        target = max(0, min(self.config.capabilities.xtoys.max_intensity, target))
        self.target_intensity = target
        if target != current:
            # DEPRECATED by Codex: xtoys.ramp_intensity used browser automation.
            # Ramp through the shared coordinator, rechecking the stop gate each step.
            sent = True
            for step in range(1, 6):
                if not await self._set_device(round(current + (target - current) * step / 5)):
                    sent = False
                    break
                self.state.intensity = int(round(coordinator.current_value))
                if step < 5:
                    await asyncio.sleep(0.2)
            if sent:
                self.last_error = ""
                self._error_count = 0
            else:
                self._error_count += 1
                self.last_error = "Intiface: команда отклонена; физический результат не подтверждён"
                logger.warning("Dorch ramp failed: %s", self.last_error)
                await self._zero_device()
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
                    # A model proposal is not an applied or physically observed value.
                    self.target_intensity = max(0, min(cap, want))
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
        if not self.config.autonomous.enabled:
            return
        self.state = SessionState()
        # UI bridge: create the event queue so phrases reach the WebUI.
        if self.state.ui_events is None:
            self.state.ui_events = asyncio.Queue()
        self._running = True
        loop = getattr(self.agent, "_loop", None)
        if loop is not None and loop.is_running():
            self._runtime_loop = loop
            self._runner = asyncio.run_coroutine_threadsafe(self._bg_loop(), loop)
            return
        self._stop_ev = threading.Event()
        self._bg_thread = threading.Thread(target=self._bg_run, name="uni.autonomous", daemon=True)
        self._bg_thread.start()

    async def _queue_runner(self) -> None:
        """🤖 Единый исполнитель очереди. Один тик ~ каждые 0.35с гонит текущий
        шаг через координатор (Intiface). Не генерирует собственных движений и
        реплик — только реализует принятые шаги ControlQueue."""
        cq = self.control_queue
        if cq is None:
            return
        while not self.state.stopped:
            try:
                await cq.run_once()
            except Exception as exc:  # исполнитель не падает
                logger.warning("control_queue runner step failed: %s", exc)
            await asyncio.sleep(0.35)

    def _bg_run(self) -> None:
        """Entry point for the background thread: own asyncio loop, kept alive."""
        try:
            asyncio.run(self._bg_loop())
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"autonomous background loop died: {exc}")
        finally:
            self._running = False

    async def _bg_loop(self) -> None:
        self._runtime_loop = asyncio.get_running_loop()
        if self.coordinator is not None:
            self.coordinator._loop = self._runtime_loop
            self._stop_generation = self.coordinator.stop_generation
        # Fresh stop event bound to this loop.
        self.state.stopped_event = asyncio.Event()
        if self.state.stopped:
            self.state.stopped_event.set()
        # Browser XToys setup is not part of the physical path. Persistent
        # configuration authorizes autonomy; STOP and device presence are runtime gates.
        if self._motion_allowed():
            try:
                await self.coordinator._bridge.connect()
                await self.coordinator.acquire(AUTONOMOUS, preempt=True)
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("Intiface setup failed: %s", exc)
        self._tasks.add(asyncio.create_task(self._vision_loop(), name="uni.vision"))
        # 🤖 Единый контур: при наличии ControlQueue НЕ запускаем независимые
        # сценарии (_speech_loop с банком реплик, _device_loop с random-walk,
        # _conductor_loop с отдельным LLM-монолог). Вместо них — единый runner
        # очереди, который гонит принятые шаги через координатор.
        if self.control_queue is not None:
            self._cq_runner_task = asyncio.create_task(self._queue_runner(), name="uni.control_queue")
            self._tasks.add(self._cq_runner_task)
            self._tasks.add(asyncio.create_task(self._control_planner_loop(), name="uni.dorch_planner"))
        else:
            self._tasks.add(asyncio.create_task(self._speech_loop(), name="uni.speech"))
            self._tasks.add(asyncio.create_task(self._device_loop(), name="uni.device"))
            self._tasks.add(asyncio.create_task(self._conductor_loop(), name="uni.conductor"))
        self._tasks.add(asyncio.create_task(self._input_watcher(), name="uni.input"))
        # Keep the loop alive until stop is requested.
        try:
            await self.state.stopped_event.wait()
        finally:
            for task in list(self._tasks):
                task.cancel()
            await self._zero_device()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
            self._running = False

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
                            loop.call_soon_threadsafe(self.emergency_stop)
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
        if not self.config.autonomous.enabled:
            return
        self._running = True
        try:
            await self._bg_loop()
        finally:
            self._running = False

    async def stop(self, *, emergency: bool = True) -> None:
        self._request_stop()
        if emergency and self.coordinator is not None:
            await self.coordinator.emergency_stop()
        await self._zero_device()
        runner = getattr(self, "_runner", None)
        if runner is not None:
            await asyncio.wrap_future(runner)
