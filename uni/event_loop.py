from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from uni.brain import Brain
from uni.capabilities.registry import CapabilityRegistry
from uni.config import Config
from uni.contracts import ToolResult
from uni.state import AgentState
from uni.session_log import SessionLogger
from uni.tools import ToolExecutor
from uni.tools.definitions import get_tool_schemas
from uni.working_memory import WorkingMemory
from uni.visual_ui_operator import VisualUIOperator
from uni.workflows import AppLaunchWorkflow

console = Console()


@dataclass(frozen=True)
class DirectCommand:
    action: str
    args: dict[str, Any]


HELP_TEXT = (
    "Команды: открой XToys; интенсивность 20; выключи игрушку; подключи игрушку; паттерн wave; "
    "статус XToys; найди в интернете запрос; открой сайт example.com; "
    "что на вкладке; сделай скриншот; посмотри через камеру; "
    "смотри через камеру 10 минут; перестань смотреть в камеру; "
    "полёт фантазии про тему; выход."
)


class EventLoop:
    def __init__(
        self,
        brain: Brain,
        capabilities: CapabilityRegistry,
        memory: WorkingMemory,
        tool_executor: ToolExecutor,
        config: Config,
        role_prompt: str = "",
        session_logger: SessionLogger | None = None,
    ) -> None:
        self.brain = brain
        self.capabilities = capabilities
        self.memory = memory
        self.tool_executor = tool_executor
        self.config = config
        self.role_prompt = role_prompt
        self.session_logger = session_logger
        self.state = AgentState.IDLE
        self._running = False
        recent_messages = getattr(memory, "recent_messages", None)
        self._history: list[dict[str, str]] = recent_messages(8) if callable(recent_messages) else []
        self._pending_message: dict[str, str] | None = None
        self._audio_lock = asyncio.Lock()
        self._tool_lock = asyncio.Lock()
        self._task_slots = asyncio.Semaphore(config.agent.max_parallel_tasks)
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._camera_watch_task: asyncio.Task[None] | None = None
        self._last_intensity_request: int | None = None
        self.app_launcher = AppLaunchWorkflow(
            self.tool_executor,
            xtoys_url=config.capabilities.xtoys.url,
        )
        self._screen_watch_task: asyncio.Task[None] | None = None
        self._screen_watch_stop = asyncio.Event()
        self._screen_observations: list[dict[str, Any]] = []

    def _log(self, event: str, message: object) -> None:
        if self.session_logger is not None:
            self.session_logger.log(event, message)

    @staticmethod
    def parse_direct_command(text: str) -> DirectCommand | None:
        original = text.strip()
        lowered = original.lower().strip(" .!?,-")
        mentions_xtoys = bool(
            re.search(
                r"(?:xtoys|xtois|x[\s-]*(?:toys|twice|2)|xpress(?:\.app)?|"
                r"икс\s*(?:тойс|туйс|твайс)|экс\s*тойс|икстойс)",
                lowered,
            )
        )
        if lowered in {"помощь", "что ты умеешь", "команды"}:
            return DirectCommand("internal.help", {})
        if lowered in {"да отправляй", "отправляй", "подтверждаю отправку", "да, отправь"}:
            return DirectCommand("internal.confirm_send", {})
        audio_message = re.search(
            r"^(?:создай|сделай|запиши)\s+(?:голосовое|аудио(?:сообщение|послание)?|послание)"
            r"(?:\s+в\s+формате\s+)?\s*(?P<format>mp3|wav)?\s*[:—-]\s*(?P<text>.+)$",
            original,
            flags=re.IGNORECASE,
        )
        if audio_message:
            return DirectCommand(
                "internal.create_audio_message",
                {
                    "text": audio_message.group("text").strip(),
                    "format": (audio_message.group("format") or "wav").casefold(),
                },
            )
        if "камер" in lowered and any(
            phrase in lowered for phrase in ("перестань", "хватит", "останови", "выключи")
        ):
            return DirectCommand("internal.camera_stop", {})
        if "камер" in lowered and re.search(r"\b(?:смотри|наблюдай|следи)\b", lowered):
            duration_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(секунд\w*|минут\w*|час\w*)",
                lowered,
            )
            seconds: float | None = None
            if "полчас" in lowered:
                seconds = 1800.0
            elif duration_match:
                amount = float(duration_match.group(1).replace(",", "."))
                unit = duration_match.group(2)
                seconds = amount * (3600 if unit.startswith("час") else 60 if unit.startswith("мин") else 1)
            elif re.search(r"(?:^|\s)(?:один\s+)?час(?:\s|$)", lowered):
                seconds = 3600.0
            return DirectCommand("internal.camera_watch", {"seconds": seconds})
        if "камер" in lowered and any(
            phrase in lowered
            for phrase in (
                "посмотри",
                "погляди",
                "оглядись",
                "что у меня",
                "что видно",
                "запусти",
                "включи",
                "открой",
            )
        ):
            return DirectCommand("internal.camera_look", {})
        message = re.search(
            r"^(?:пусть\s+юни\s+)?(?:подготовь|напиши)\s+(?:сообщение\s+)?(?:для\s+контакта\s+)?(?P<contact>[а-яёa-z0-9_ -]{1,80})\s*[:—-]\s*(?P<text>.+)$",
            original,
            flags=re.IGNORECASE,
        )
        if message:
            contact = message.group("contact").strip()
            if contact.casefold() == "асе":
                contact = "Ася"
            return DirectCommand(
                "internal.draft_message",
                {"contact": contact, "text": message.group("text").strip()},
            )
        if mentions_xtoys and any(word in lowered for word in ("открой", "открывай", "покажи", "перейди")):
            return DirectCommand("xtoys.open", {})
        if any(
            phrase in lowered
            for phrase in (
                "ничего не меняет",
                "ничего не меняется",
                "не сработало",
                "не работает",
            )
        ):
            return DirectCommand("internal.retry_intensity_visual", {})
        imagination = re.search(r"(?:пол[её]т\s+фантазии|пофантазируй|самостоятельно\s+поисследуй)(?:\s+(?:про|на тему))?\s*(.*)$", original, flags=re.IGNORECASE)
        if imagination:
            topic = imagination.group(1).strip() or "необычные природные явления"
            return DirectCommand("internal.explore", {"topic": topic})
        intensity = re.search(
            r"(?:интенсивност\w*|мощност\w*|скорост\w*)\D{0,30}(\d{1,3})",
            lowered,
        )
        if intensity:
            return DirectCommand("xtoys.set_intensity", {"value": int(intensity.group(1))})
        if any(word in lowered for word in ("интенсивност", "мощност", "скорост")):
            return DirectCommand(
                "internal.response",
                {"text": "Назовите конкретное значение от 0 до защитного максимума, например: интенсивность 5."},
            )
        pattern = re.search(r"(?:паттерн|режим)\s+(.+)$", original, flags=re.IGNORECASE)
        if pattern:
            return DirectCommand("xtoys.select_pattern", {"pattern": pattern.group(1).strip()})
        if mentions_xtoys and any(word in lowered for word in ("статус", "состояние", "что с")):
            return DirectCommand("xtoys.get_status", {})
        if "выключи игруш" in lowered:
            return DirectCommand("xtoys.set_intensity", {"value": 0})
        if "включи игруш" in lowered:
            return DirectCommand("internal.response", {"text": "Назовите безопасную интенсивность, например: интенсивность 10"})
        if any(word in lowered for word in ("подключи игруш", "переключи игруш")):
            return DirectCommand("xtoys.toggle", {})
        image_search = re.search(
            r"^(?:найди|поищи|поиск(?:ай)?|покажи)(?:\s+в\s+интернете)?\s+(?:среди\s+картинок|картинки|изображения|фото(?:графии)?)\s+(.+)$",
            original,
            flags=re.IGNORECASE,
        )
        if not image_search:
            image_search = re.search(
                r"^(?:найди|поищи|поиск(?:ай)?|покажи)(?:\s+в\s+интернете)?\s+(.+?)\s+(?:среди\s+картинок|в\s+картинках|в\s+изображениях)$",
                original,
                flags=re.IGNORECASE,
            )
        if image_search:
            return DirectCommand("browser.search_images", {"query": image_search.group(1).strip()})
        search = re.search(
            r"^(?:найди|поищи|поиск(?:ай)?)(?:\s+в\s+интернете|\s+в\s+сети)?\s+(.+)$",
            original,
            flags=re.IGNORECASE,
        )
        if search:
            return DirectCommand("browser.search_web", {"query": search.group(1).strip()})
        url = re.search(
            r"^(?:открой|перейди(?:\s+на)?)(?:\s+сайт)?\s+((?:https?://)?[\w.-]+\.[a-zа-я]{2,}(?:/\S*)?)$",
            original,
            flags=re.IGNORECASE,
        )
        if url:
            return DirectCommand("browser.navigate", {"url": url.group(1)})
        if any(
            phrase in lowered
            for phrase in (
                "что на экране",
                "что на вкладке",
                "опиши экран",
                "посмотри экран",
                "посмотри на экран",
                "посмотри вкладку",
                "скажи что ты видишь",
                "скажи, что ты видишь",
            )
        ):
            return DirectCommand("vision.analyze_screen", {"prompt": original})
        if any(phrase in lowered for phrase in ("сделай скриншот", "сними экран", "сохрани скриншот")):
            return DirectCommand("browser.save_screenshot", {"label": "manual"})
        if any(phrase in lowered for phrase in ("какая вкладка", "текущая вкладка", "где мы в браузере")):
            return DirectCommand("browser.current_tab", {})
        # Event-driven screen watch (OFF by default; VLM only on screen change).
        if any(phrase in lowered for phrase in ("следи за экраном", "наблюдай за экраном", "следи за экраном")):
            return DirectCommand("internal.watch_screen", {})
        if any(phrase in lowered for phrase in ("перестань следить за экраном", "хватит следить за экраном", "останови наблюдение")):
            return DirectCommand("internal.watch_screen_stop", {})
        return None

    @staticmethod
    def is_stop_command(text: str) -> bool:
        normalized = " ".join(text.casefold().split())
        return any(
            token in normalized
            for token in ("стоп", "красный", "аварийный стоп", "выход", "остановись",
                         "немедленно стой", "заверши работу", "пока", "exit", "quit")
        )

    # --- Hands-free mode bridge ----------------------------------------------
    def _autonomous(self):
        """Lazily resolve the AutonomousController created by Agent."""
        return getattr(getattr(self, "_agent_ref", None), "autonomous", None)

    async def _maybe_autonomous_override(self, user_input: str) -> bool:
        """If the hands-free session is running, route stop + manual intensity to it.

        Returns True if the input was consumed by the autonomous controller.
        """
        ctrl = self._autonomous()
        if ctrl is None or not getattr(ctrl, "device_allowed", False):
            return False
        if ctrl.state.stopped and self.is_stop_command(user_input):
            return False  # already stopped; let normal flow handle it
        # stop / red -> emergency stop, not via the task queue
        if self.is_stop_command(user_input):
            console.print("[bold red]АВАРИЙНЫЙ СТОП — интенсивность 0[/bold red]")
            ctrl.emergency_stop()
            return True
        # manual intensity -> adopt value and pause the auto timeline briefly
        m = re.search(r"(?:интенсивность|скорость|speed)\s*{0,3}(\d{1,3})", user_input.casefold())
        if m:
            value = max(0, min(100, int(m.group(1))))
            res = await ctrl._run_tool("xtoys.ramp_intensity", {"value": value, "steps": 3})
            if res.success:
                ctrl.state.intensity = value
                ctrl.request_manual_override(seconds=45.0)
                await self._speak(f"Приняла, поставила {value}%. Сама пока не трогаю — скажи, если снова управлять.")
                return True
        return False

    async def _speak(self, text: str) -> bool:
        if not text or not self.config.agent.speak_responses:
            return False
        spoken = self._spoken_excerpt(text)
        self._log("SPEECH", spoken)
        if len(spoken) < len(text.strip()):
            console.print("[dim]Голосовой ответ сокращён; полный текст выше. Esc прерывает речь.[/dim]")
        async with self._audio_lock:
            self.state = AgentState.SPEAKING
            result = await self.tool_executor.execute("speech.speak", {"text": spoken})
        if not result.success:
            console.print(f"[yellow]TTS: {result.message}[/yellow]")
        return result.success

    def _spoken_excerpt(self, text: str) -> str:
        limit = self.config.agent.spoken_response_max_chars
        clean = " ".join(text.split())
        if len(clean) <= limit:
            return clean
        candidate = clean[: limit + 1]
        boundaries = [candidate.rfind(mark) for mark in (".", "!", "?")]
        boundary = max(boundaries)
        if boundary >= max(40, limit // 3):
            return candidate[: boundary + 1]
        return clean[: limit - 1].rstrip() + "…"

    def _clean_answer(self, text: str) -> str:
        clean = re.sub(r"(?im)^\s*stile\s*=\s*[^\n]+\s*$", "", str(text)).strip()
        clean = re.sub(r"\n{3,}", "\n\n", clean)
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        if len(sentences) > 3:
            clean = " ".join(sentences[:3])
        limit = self.config.agent.response_max_chars
        if len(clean) > limit:
            candidate = clean[: limit + 1]
            boundary = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
            clean = candidate[: boundary + 1] if boundary >= 80 else clean[: limit - 1].rstrip() + "…"
        return clean or "Не удалось сформировать ответ."

    async def _listen_once(self) -> str:
        async with self._audio_lock:
            self.state = AgentState.LISTENING
            duration = self.config.capabilities.speech.listen_duration
            console.print("[cyan]Слушаю... говорите обычным голосом[/cyan]")
            result = await self.tool_executor.execute("speech.listen", {"duration": duration})
        if result.success and isinstance(result.data, str):
            console.print(f"[yellow]Вы: {result.data}[/yellow]")
            return result.data
        return ""

    @staticmethod
    def _result_text(action: str, result: ToolResult) -> str:
        if not result.success:
            return result.message
        data = result.data
        if action == "browser.search_web" and isinstance(data, dict):
            results = data.get("results") or []
            titles = [item.get("title", "") for item in results[:3] if isinstance(item, dict)]
            suffix = ". ".join(title for title in titles if title)
            return result.message + (f". Первые результаты: {suffix}" if suffix else "")
        if action == "vision.analyze_screen" and isinstance(data, dict):
            return str(data.get("analysis") or result.message)
        if action in {"xtoys.get_status", "browser.extract_text"} and isinstance(data, dict):
            visible = data.get("visible_text") or data.get("text")
            if visible:
                return str(visible)[:700]
        return result.message

    async def _execute_direct(self, command: DirectCommand) -> str:
        if command.action == "internal.help":
            return HELP_TEXT
        if command.action == "internal.response":
            return str(command.args.get("text", ""))
        if command.action == "internal.draft_message":
            return await self._draft_visual_message(
                str(command.args.get("contact", "")),
                str(command.args.get("text", "")),
            )
        if command.action == "internal.confirm_send":
            return await self._confirm_visual_message()
        if command.action == "internal.retry_intensity_visual":
            if self._last_intensity_request is None:
                return "Сначала назовите конкретную интенсивность, например: интенсивность 5."
            return await self._set_intensity_visually(self._last_intensity_request)
        if command.action == "internal.explore":
            return await self._explore_web(str(command.args.get("topic", "")))
        if command.action == "internal.camera_look":
            return await self._camera_look()
        if command.action == "internal.camera_watch":
            seconds = command.args.get("seconds")
            return await self._start_camera_watch(float(seconds) if seconds is not None else None)
        if command.action == "internal.watch_screen":
            return await self._start_screen_watch()
        if command.action == "internal.watch_screen_stop":
            return await self._stop_screen_watch(announce=True)
        if command.action == "internal.camera_stop":
            return await self._stop_camera_watch(announce=False)
        if command.action == "internal.create_audio_message":
            return await self._create_audio_message(
                str(command.args.get("text", "")),
                str(command.args.get("format", "wav")),
            )
        if command.action == "xtoys.open":
            # Orchestration-level launch: recovers BrowserSession, optional UI fallback.
            # Not handled inside the capability (no-capability-calls-capability rule).
            result = await self.app_launcher.open_xtoys()
            style = "green" if result.success else "red"
            console.print(f"[{style}]{'OK' if result.success else 'ERROR'}: {result.message}[/{style}]")
            return result.message
        self.state = AgentState.EXECUTING
        if command.action == "xtoys.set_intensity":
            self._last_intensity_request = max(0, min(100, int(command.args.get("value", 0))))
        console.print(f"[blue]ACTION {command.action}({command.args})[/blue]")
        result = await self._run_tool(command.action, command.args)
        style = "green" if result.success else "red"
        console.print(f"[{style}]{'OK' if result.success else 'ERROR'}: {result.message}[/{style}]")
        if (
            command.action == "xtoys.set_intensity"
            and not result.success
            and self._last_intensity_request <= self.config.capabilities.xtoys.max_intensity
            and any(marker in result.message.casefold() for marker in ("слайдер", "intensity", "контрол"))
        ):
            return await self._set_intensity_visually(self._last_intensity_request)
        answer = self._result_text(command.action, result)
        if command.action == "vision.analyze_screen" and result.success:
            localized = await self.brain.chat(
                [
                    {
                        "role": "system",
                        "content": "Переведи описание скриншота на русский. Сохрани факты, ответь максимум 3 предложениями.",
                    },
                    {"role": "user", "content": answer[:4000]},
                ],
                tools=None,
                temperature=0.1,
                max_tokens=350,
            )
            if not localized.error and localized.text:
                answer = localized.text
        return answer

    async def _set_intensity_visually(self, value: int) -> str:
        bounded = max(0, min(int(value), self.config.capabilities.xtoys.max_intensity))
        operator = VisualUIOperator(
            self.tool_executor,
            max_steps=min(8, self.config.agent.visual_ui_max_steps),
            log=self._log,
        )
        async with self._tool_lock:
            focused = await operator._run("computer.focus_window", {"title": "XToys.app"})
            if not focused.success:
                return f"Визуальная попытка остановлена: окно XToys неоднозначно или недоступно — {focused.message}"
            result = await operator.set_vertical_slider(
                "the visible vertical XToys intensity control labelled Speed with a numeric value",
                bounded,
            )
        if not result.success:
            return f"DOM-управление не сработало, и Vision не смог безопасно нажать слайдер: {result.message}"
        return (
            f"Юни визуально навела мышь и нажала Speed на уровне {bounded}%. "
            "Изменение интерфейса проверено свежим снимком; физическая реакция устройства не подтверждена."
        )

    async def _draft_visual_message(self, contact: str, text: str) -> str:
        if not contact or not text:
            return "Для сообщения нужны контакт и текст."
        operator = VisualUIOperator(
            self.tool_executor,
            max_steps=self.config.agent.visual_ui_max_steps,
            log=self._log,
        )
        async with self._tool_lock:
            result = await operator.draft_telegram_message(contact, text, account="uni")
        if not result.success:
            return f"Не удалось подготовить сообщение: {result.message}"
        self._pending_message = {
            "app": "telegram_uni",
            "account": "uni",
            "contact": contact,
            "text": text,
        }
        return (
            f"Черновик для {contact} готов: «{text}». "
            "Он ещё не отправлен. Скажите «да, отправляй» для подтверждения."
        )

    async def _confirm_visual_message(self) -> str:
        pending = self._pending_message
        if not isinstance(pending, dict) or pending.get("app") != "telegram_uni":
            return "Нет подготовленного сообщения для отправки."
        operator = VisualUIOperator(
            self.tool_executor,
            max_steps=4,
            log=self._log,
        )
        async with self._tool_lock:
            result = await operator.send_focused_draft(account=str(pending.get("account", "uni")))
        if not result.success:
            return f"Сообщение не отправлено: {result.message}"
        contact = str(pending.get("contact", "контакту"))
        self._pending_message = None
        return f"Сообщение для {contact} отправлено."

    async def _run_tool(self, action: str, args: dict[str, Any]) -> ToolResult:
        self._log("ACTION", f"{action} {args}")
        async with self._tool_lock:
            result = await self.tool_executor.execute(action, args)
        self._log("RESULT", f"{action}: {result.message}")
        return result

    async def _create_audio_message(self, text: str, audio_format: str) -> str:
        clean_text = text.strip()
        output_format = audio_format.casefold().strip()
        if not clean_text:
            return "Текст аудиопослания пуст."
        if output_format not in {"wav", "mp3"}:
            return "Поддерживаются только WAV и MP3."
        root = (
            self.session_logger.session_dir
            if self.session_logger is not None
            else Path(self.config.logging.directory).resolve() / "audio-messages"
        )
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = (root / "audio_messages" / f"uni_message_{timestamp}.{output_format}").resolve()
        result = await self._run_tool(
            "speech.synthesize_file",
            {"text": clean_text, "path": str(path), "format": output_format},
        )
        if not result.success or not isinstance(result.data, dict):
            return f"Не удалось создать аудиопослание: {result.message}"
        self._log("AUDIO_MESSAGE", result.data)
        return (
            f"Аудиопослание создано и пока никому не отправлено: {result.data['path']}. "
            "Для отправки назовите контакт; перед отправкой я отдельно попрошу подтверждение."
        )

    async def _camera_look(self) -> str:
        if not self.config.capabilities.camera.enabled:
            return "Камера отключена в config.yaml."
        announced = await self._speak("Я включаю камеру и сейчас посмотрю, что видно в комнате.")
        if not announced:
            return "Камеру не включила: не удалось произнести обязательное уведомление."
        self._log("CAMERA_NOTICE", "Однократный просмотр камеры объявлен вслух")
        started = await self._run_tool("camera.start", {"notice_ack": True})
        if not started.success:
            return f"Камера не включилась: {started.message}"
        try:
            frame = await self._run_tool("camera.snapshot", {"label": "look"})
        finally:
            await self._run_tool("camera.stop", {})
        if not frame.success or not isinstance(frame.data, dict):
            return f"Я выключила камеру, но не получила кадр: {frame.message}"
        path = str(frame.data.get("path", ""))
        brightness = float(frame.data.get("brightness", 0.0))
        self._log("CAMERA_FRAME", f"{path} brightness={brightness:.2f}")
        if brightness < self.config.capabilities.camera.min_brightness:
            return (
                "Я закончила смотреть и выключила камеру. Кадр почти полностью тёмный, "
                "поэтому надёжно определить обстановку сейчас нельзя."
            )
        analysis = await self._run_tool(
            "vision.analyze_file",
            {
                "path": path,
                "prompt": (
                    "Describe only what is visibly present in this webcam frame of a room. "
                    "Mention people, animals, major objects, lighting, and anything unusual. "
                    "Do not infer identity, private facts, or events outside the image."
                ),
            },
        )
        if not analysis.success or not isinstance(analysis.data, dict):
            return f"Я уже выключила камеру. Кадр сохранён, но Vision не ответил: {analysis.message}"
        description = str(analysis.data.get("analysis", analysis.message)).strip()
        if self.brain is not None:
            localized = await self.brain.chat(
                [
                    {
                        "role": "system",
                        "content": "Переведи описание кадра камеры на русский. Сохрани только видимые факты, максимум 3 предложения.",
                    },
                    {"role": "user", "content": description[:4000]},
                ],
                tools=None,
                temperature=0.1,
                max_tokens=350,
            )
            if not localized.error and localized.text:
                description = localized.text.strip()
        self._log("CAMERA_OBSERVATION", description)
        return f"Я закончила смотреть и выключила камеру. На кадре: {description}"

    async def _camera_watch_worker(self, duration_s: float) -> None:
        camera_config = self.config.capabilities.camera
        started_at = asyncio.get_running_loop().time()
        ends_at = started_at + duration_s
        next_sample = started_at
        next_reminder = started_at + camera_config.reminder_interval_seconds
        completed_normally = False
        try:
            while True:
                now = asyncio.get_running_loop().time()
                if now >= ends_at:
                    completed_normally = True
                    break
                if now >= next_sample:
                    frame = await self._run_tool("camera.snapshot", {"label": "watch"})
                    if frame.success and isinstance(frame.data, dict):
                        path = str(frame.data.get("path", ""))
                        brightness = float(frame.data.get("brightness", 0.0))
                        self._log("CAMERA_FRAME", f"{path} brightness={brightness:.2f}")
                        if brightness < camera_config.min_brightness:
                            self._log("CAMERA_OBSERVATION", "Кадр слишком тёмный для надёжного анализа")
                            next_sample = now + camera_config.sample_interval_seconds
                            await asyncio.sleep(0)
                            continue
                        analysis = await self._run_tool(
                            "vision.analyze_file",
                            {
                                "path": path,
                                "prompt": (
                                    "Briefly describe this room webcam frame and any visible change or unusual event. "
                                    "Do not infer identity or facts outside the image."
                                ),
                            },
                        )
                        if analysis.success and isinstance(analysis.data, dict):
                            self._log("CAMERA_OBSERVATION", analysis.data.get("analysis", ""))
                    next_sample = now + camera_config.sample_interval_seconds
                if now >= next_reminder:
                    await self._speak("Напоминаю: я всё ещё наблюдаю через камеру.")
                    self._log("CAMERA_NOTICE", "Периодическое звуковое напоминание")
                    next_reminder = now + camera_config.reminder_interval_seconds
                delay = min(1.0, max(0.05, ends_at - now), max(0.05, next_sample - now), max(0.05, next_reminder - now))
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        finally:
            await self._run_tool("camera.stop", {})
            self._camera_watch_task = None
            if completed_normally:
                self._log("CAMERA_NOTICE", "Длительное наблюдение завершено")
                await self._speak("Я закончила наблюдение и выключила камеру.")

    async def _start_camera_watch(self, seconds: float | None) -> str:
        if not self.config.capabilities.camera.enabled:
            return "Камера отключена в config.yaml."
        if self._camera_watch_task is not None and not self._camera_watch_task.done():
            return "Я уже наблюдаю через камеру."
        camera_config = self.config.capabilities.camera
        duration_s = seconds if seconds is not None else camera_config.default_watch_seconds
        duration_s = min(max(10.0, duration_s), camera_config.max_watch_seconds)
        minutes = duration_s / 60
        announced = await self._speak(
            f"Я начинаю наблюдение через камеру примерно на {minutes:g} минут. "
            "Если оно затянется, я буду напоминать об этом каждые тридцать минут."
        )
        if not announced:
            return "Камеру не включила: не удалось произнести обязательное уведомление."
        self._log("CAMERA_NOTICE", f"Начало наблюдения на {duration_s:g} секунд объявлено вслух")
        started = await self._run_tool("camera.start", {"notice_ack": True})
        if not started.success:
            return f"Камера не включилась: {started.message}"
        self._camera_watch_task = asyncio.create_task(self._camera_watch_worker(duration_s))
        return f"Наблюдение через камеру запущено на {minutes:g} минут."

    async def _stop_camera_watch(self, announce: bool = True) -> str:
        task = self._camera_watch_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            await self._run_tool("camera.stop", {})
        self._camera_watch_task = None
        message = "Я перестала смотреть и выключила камеру."
        if announce:
            await self._speak(message)
        self._log("CAMERA_NOTICE", message)
        return message

    # --- Event-driven screen watch (OFF by default) ------------------------
    _SENSITIVE_URL_HINTS = (
        "password", "account/login", "online-bank", "bank", "telegram",
        "web.whatsapp", "mail", "private", "auth", "signin",
    )

    @staticmethod
    def _is_sensitive_url(url: str) -> bool:
        low = url.lower()
        return any(hint in low for hint in EventLoop._SENSITIVE_URL_HINTS)

    @staticmethod
    def _screenshot_hash(path: str | None) -> str:
        """Cheap change detector: imagehash if available, else file size."""
        if not path:
            return ""
        try:
            from pathlib import Path as _P
            import imagehash  # type: ignore
            from PIL import Image  # type: ignore

            return str(imagehash.average_hash(Image.open(_P(path))))
        except Exception:
            try:
                return str(_P := __import__("pathlib").Path(path).stat().st_size)
            except Exception:
                return ""

    async def _start_screen_watch(self, interval: float = 15.0) -> str:
        if self._screen_watch_task is not None and not self._screen_watch_task.done():
            return "Я уже слежу за экраном."
        interval = min(max(10.0, interval), 60.0)
        announced = await self._speak(
            "Я начинаю следить за экраном. Это можно в любой момент прервать голосом "
            "или командой 'перестань следить за экраном'."
        )
        if not announced:
            return "Наблюдение не запущено: не удалось произнести обязательное уведомление."
        self._log("SCREEN_WATCH", f"старт, интервал {interval:g}s, VLM только при изменении")
        self._screen_watch_task = asyncio.create_task(self._watch_screen_loop(interval))
        return "Слежу за экраном. Буду озвучивать только существенные изменения."

    async def _stop_screen_watch(self, announce: bool = True) -> str:
        task = self._screen_watch_task
        if task is not None and not task.done():
            self._screen_watch_stop.set()
            await asyncio.gather(task, return_exceptions=True)
        self._screen_watch_task = None
        self._screen_watch_stop.clear()
        message = "Я перестала следить за экраном."
        if announce:
            await self._speak(message)
        self._log("SCREEN_WATCH", "стоп")
        return message

    async def _watch_screen_loop(self, interval: float) -> None:
        prev_hash = ""
        while not self._screen_watch_stop.is_set():
            # Pause on sensitive windows (passwords, banks, messengers).
            tab = await self._run_tool("browser.current_tab", {})
            if tab.success and isinstance(tab.data, dict):
                url = str(tab.data.get("url", ""))
                if self._is_sensitive_url(url):
                    await asyncio.sleep(interval)
                    continue
            shot = await self._run_tool("browser.save_screenshot", {"label": "watch"})
            if shot.success and isinstance(shot.data, dict):
                h = self._screenshot_hash(shot.data.get("path"))
                if h and h != prev_hash:
                    prev_hash = h
                    analysis = await self._run_tool(
                        "vision.analyze_screen",
                        {"prompt": "Кратко опиши, что изменилось на экране (максимум 2 предложения)."},
                    )
                    if analysis.success:
                        # Temporary Observation, NOT a permanent memory fact.
                        self._screen_observations.append(
                            {
                                "timestamp": time.time(),
                                "confidence": 0.5,
                                "analysis": analysis.message,
                            }
                        )
                        if len(self._screen_observations) > 50:
                            self._screen_observations.pop(0)
                        await self._speak(analysis.message)
            await asyncio.sleep(interval)

    async def shutdown(self) -> None:
        if self._screen_watch_task is not None and not self._screen_watch_task.done():
            await self._stop_screen_watch(announce=False)
        if self._camera_watch_task is not None and not self._camera_watch_task.done():
            await self._stop_camera_watch(announce=True)
        else:
            await self._run_tool("camera.stop", {})

    async def _next_exploration_query(self, current: str, observation: str, step: int) -> tuple[str, str]:
        response = await self.brain.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты выбираешь следующий безопасный шаг любознательного поиска по изображениям. "
                        "Не предлагай вход, формы, покупки, скачивания, взрослый контент или изменение сайтов. "
                        "Верни только JSON: {\"thought\": \"краткая мысль вслух\", "
                        "\"next_query\": \"следующий поисковый запрос\"}. Это публичное резюме, не скрытая цепочка рассуждений."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Шаг {step}. Текущий запрос: {current}. Наблюдение: {observation[:1800]}",
                },
            ],
            tools=None,
            temperature=0.6,
            max_tokens=180,
        )
        fallback = (f"{current} сравнение размеров", f"Интересно сравнить изображения по теме «{current}».")
        if response.error or not response.text:
            return fallback
        try:
            raw = response.text.strip()
            fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
            data = json.loads(fenced.group(1) if fenced else raw)
            query = str(data.get("next_query", "")).strip()[:180]
            thought = str(data.get("thought", "")).strip()[:500]
            if not query or not thought:
                return fallback
            return query, thought
        except (ValueError, TypeError, json.JSONDecodeError):
            return fallback

    async def _explore_web(self, topic: str) -> str:
        query = topic.strip()[:180] or "необычные природные явления"
        summaries: list[str] = []
        for step in range(1, self.config.agent.exploration_steps + 1):
            thought = f"Шаг {step}: ищу изображения по теме «{query}»."
            self._log("THOUGHT", thought)
            await self._speak(thought)
            search_result = await self._run_tool("browser.search_images", {"query": query})
            if not search_result.success:
                return f"Исследование остановлено: {search_result.message}"
            screenshot_result = await self._run_tool(
                "browser.save_screenshot", {"label": f"explore_{step}_{query[:40]}"}
            )
            observation_result = await self._run_tool(
                "vision.analyze_screen",
                {"prompt": "Кратко опиши видимые результаты поиска изображений и назови самое интересное безопасное направление для продолжения."},
            )
            observation = self._result_text("vision.analyze_screen", observation_result)
            summaries.append(observation[:500])
            if screenshot_result.success and isinstance(screenshot_result.data, dict):
                self._log("SCREENSHOT", screenshot_result.data.get("path", ""))
            if step < self.config.agent.exploration_steps:
                query, next_thought = await self._next_exploration_query(query, observation, step)
                self._log("THOUGHT", next_thought)
                await self._speak(next_thought)
        return f"Исследование завершено за {len(summaries)} шага. Скриншоты и журнал сохранены в папке сессии."

    async def _free_form(self, user_input: str) -> str:
        self.state = AgentState.THINKING
        default_prompt = "Ты UNI, локальный голосовой помощник."
        system = (
            (self.role_prompt or default_prompt)
            + "\n\n## Runtime rules\n"
            "Отвечай по-русски, коротко, максимум 3 предложения. "
            "Для браузера, поиска и XToys используй доступные функции. Не заявляй, что физическое "
            "состояние XToys подтверждено, если инструмент пишет verified=false. "
            "Не превышай запрошенную пользователем интенсивность.\n\nПамять:\n"
            + self.memory.get_context(self.config.memory.max_context_tokens)
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            *self._history[-8:],
            {"role": "user", "content": user_input},
        ]
        response = await self.brain.chat(
            messages,
            tools=get_tool_schemas(set(self.capabilities.get_names())),
        )
        if response.error:
            return (
                "LM Studio сейчас недоступен. Прямые команды браузера, поиска и XToys работают; "
                "для свободного диалога запустите Local Server на порту 1234."
            )
        if not response.tool_calls:
            answer = response.text or "Не удалось сформировать ответ."
            return answer

        tool_summaries: list[str] = []
        for call in response.tool_calls[:3]:
            result = await self._run_tool(call.name, call.arguments)
            canonical = self.tool_executor.canonical_name(call.name)
            console.print(f"[blue]ACTION {canonical}({call.arguments})[/blue]")
            console.print(f"[{'green' if result.success else 'red'}]{result.message}[/]")
            tool_summaries.append(f"{canonical}: {self._result_text(canonical, result)}")
        compact = "\n".join(tool_summaries)[:6000]
        final = await self.brain.chat(
            [
                {"role": "system", "content": "Кратко сообщи пользователю результат выполненных инструментов. Не выдумывай успех."},
                {"role": "user", "content": compact},
            ]
        )
        answer = final.text if not final.error and final.text else compact
        return answer

    async def _process_input(self, user_input: str) -> str:
        # Hands-free override has priority so stop/manual intensity are instant.
        if await self._maybe_autonomous_override(user_input):
            return "ok"
        self._log("USER", user_input)
        console.print(f"[bold]Команда:[/bold] {user_input}")
        direct = self.parse_direct_command(user_input)
        answer = await self._execute_direct(direct) if direct else await self._free_form(user_input)
        answer = self._clean_answer(answer)
        self._history.extend(
            [{"role": "user", "content": user_input}, {"role": "assistant", "content": answer}]
        )
        self._history = self._history[-16:]
        append_exchange = getattr(self.memory, "append_exchange", None)
        if callable(append_exchange):
            append_exchange(user_input, answer)
        console.print(f"[green]UNI: {answer}[/green]")
        self._log("ASSISTANT", answer)
        await self._speak(answer)
        return answer

    async def _run_background_input(self, user_input: str) -> None:
        try:
            async with self._task_slots:
                async with asyncio.timeout(self.config.agent.task_timeout_seconds):
                    await self._process_input(user_input)
        except TimeoutError:
            message = "Задача превысила лимит времени и остановлена. Можно дать новую команду."
            console.print(f"[red]{message}[/red]")
            await self._speak(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state = AgentState.ERROR
            console.print(f"[red]Ошибка фоновой задачи: {exc}[/red]")

    def _schedule_input(self, user_input: str) -> bool:
        if len(self._background_tasks) >= self.config.agent.max_pending_tasks:
            console.print("[yellow]Очередь заполнена; повторите команду чуть позже.[/yellow]")
            return False
        task = asyncio.create_task(self._run_background_input(user_input))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        console.print("[dim]Приняла; можно говорить следующую команду.[/dim]")
        return True

    async def _shutdown_background_tasks(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _voice_input_producer(self, queue: asyncio.Queue[tuple[str, str]]) -> None:
        while self._running:
            text = await self._listen_once()
            if text:
                await queue.put(("voice", text.strip()))
            else:
                await asyncio.sleep(0.05)

    @staticmethod
    def _text_input_worker(
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[tuple[str, str]],
        stopped: threading.Event,
    ) -> None:
        while not stopped.is_set():
            try:
                text = input("\nВы (текст): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if text and not stopped.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, ("text", text))

    async def _run_mixed_input(self) -> None:
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        stopped = threading.Event()
        loop = asyncio.get_running_loop()
        threading.Thread(
            target=self._text_input_worker,
            args=(loop, queue, stopped),
            name="uni-text-input",
            daemon=True,
        ).start()
        voice_task = asyncio.create_task(self._voice_input_producer(queue))
        console.print("[cyan]Можно говорить или печатать. Enter отправляет текст; ответы UNI звучат вслух.[/cyan]")
        try:
            while self._running:
                _source, user_input = await queue.get()
                if self.is_stop_command(user_input):
                    self._running = False
                    await self._speak("До встречи")
                    break
                self._schedule_input(user_input)
        finally:
            stopped.set()
            voice_task.cancel()
            await asyncio.gather(voice_task, return_exceptions=True)

    async def run_cycle(self, user_input: Optional[str] = None):
        if not user_input:
            user_input = await self._listen_once()
        if not user_input:
            self.state = AgentState.IDLE
            return None
        if self.is_stop_command(user_input):
            ctrl = self._autonomous()
            if ctrl is not None and getattr(ctrl, "device_allowed", False) and not ctrl.state.stopped:
                console.print("[bold red]АВАРИЙНЫЙ СТОП — интенсивность 0[/bold red]")
                ctrl.emergency_stop()
            self._running = False
            await self._speak("До встречи")
            self.state = AgentState.IDLE
            return "stop"
        answer = await self._process_input(user_input)
        self.state = AgentState.IDLE
        return answer

    async def run_interactive(self):
        self._running = True
        mode = self.config.agent.input_mode.lower()
        console.print(f"[cyan]{HELP_TEXT}[/cyan]")
        try:
            if mode == "mixed":
                await self._run_mixed_input()
                return
            while self._running:
                try:
                    if mode == "text":
                        user_input = (await asyncio.to_thread(input, "> ")).strip()
                    else:
                        user_input = await self._listen_once()
                    if not user_input:
                        await asyncio.sleep(0.05)
                        continue
                    if self.is_stop_command(user_input):
                        ctrl = self._autonomous()
                        if ctrl is not None and getattr(ctrl, "device_allowed", False) and not ctrl.state.stopped:
                            console.print("[bold red]АВАРИЙНЫЙ СТОП — интенсивность 0[/bold red]")
                            ctrl.emergency_stop()
                        self._running = False
                        await self._speak("До встречи")
                        break
                    self._schedule_input(user_input)
                    await asyncio.sleep(0.05)
                except KeyboardInterrupt:
                    self._running = False
                except Exception as exc:
                    self.state = AgentState.ERROR
                    console.print(f"[red]Ошибка цикла: {exc}[/red]")
                    await asyncio.sleep(0.5)
        finally:
            await self._shutdown_background_tasks()
            self.state = AgentState.IDLE
