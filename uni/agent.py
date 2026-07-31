from __future__ import annotations

import asyncio
from typing import Optional

from rich.console import Console

from uni.brain import Brain
from uni.browser_session import BrowserSession
from uni.capabilities.browser import BrowserCapability
from uni.capabilities.camera import CameraCapability
from uni.capabilities.computer import ComputerCapability
from uni.capabilities.memory import MemoryCapability
from uni.capabilities.registry import CapabilityRegistry
from uni.capabilities.speech import SpeechCapability
from uni.capabilities.vision import VisionCapability
from uni.capabilities.xtoys import XToysCapability
from uni.config import Config
from uni.event_loop import EventLoop
from uni.roles.loader import RoleLoader
from uni.session_log import SessionLogger
from uni.tools import ToolExecutor
from uni.working_memory import WorkingMemory

console = Console()


class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.session_logger = SessionLogger(config.logging.directory, config.logging.enabled)
        self.brain = Brain(config.brain, vision_model=config.capabilities.vision.model)
        self.memory = WorkingMemory(
            config.memory.path,
            max_dialogue_turns=config.memory.max_dialogue_turns,
        )
        browser_config = config.capabilities.browser
        self.browser_session = BrowserSession(
            headless=browser_config.headless,
            viewport_width=browser_config.viewport_width,
            viewport_height=browser_config.viewport_height,
            channel=browser_config.channel,
            user_data_dir=browser_config.user_data_dir,
            search_engine=browser_config.search_engine,
            image_search_engine=browser_config.image_search_engine,
        )

        speech_config = config.capabilities.speech
        speech = SpeechCapability(
            stt_model=speech_config.stt_model,
            stt_device=speech_config.stt_device,
            stt_compute_type=speech_config.stt_compute_type,
            stt_beam_size=speech_config.stt_beam_size,
            microphone_gain=speech_config.microphone_gain,
            voice_activation_threshold=speech_config.voice_activation_threshold,
            voice_silence_seconds=speech_config.voice_silence_seconds,
            max_utterance_seconds=speech_config.max_utterance_seconds,
            tts_provider=speech_config.tts_provider,
            tts_voice=speech_config.tts_voice,
            silero_model=speech_config.silero_model,
            silero_speaker=speech_config.silero_speaker,
            silero_sample_rate=speech_config.silero_sample_rate,
            sample_rate=speech_config.sample_rate,
            input_device=speech_config.input_device,
            output_device=speech_config.output_device,
        )
        self.speech = speech
        speech._session_logger = self.session_logger
        self.role = RoleLoader().load(config.agent.default_role)
        computer = ComputerCapability(
            use_uia=config.capabilities.computer.use_uia,
            failsafe=config.capabilities.computer.failsafe,
            mouse_move_duration=config.capabilities.computer.mouse_move_duration,
        )
        camera_config = config.capabilities.camera
        camera = CameraCapability(
            self.session_logger.session_dir / "camera",
            device_index=camera_config.device_index,
            backend=camera_config.backend,
            width=camera_config.width,
            height=camera_config.height,
        )
        browser = BrowserCapability(self.browser_session, self.session_logger.screenshot_dir)
        vision = VisionCapability(self.brain, config, self.browser_session)
        memory_capability = MemoryCapability(self.memory)
        xtoys_config = config.capabilities.xtoys
        xtoys = XToysCapability(
            self.browser_session,
            url=xtoys_config.url,
            max_intensity=xtoys_config.max_intensity,
        )

        self.capabilities = CapabilityRegistry()
        for capability in (speech, computer, camera, browser, vision, memory_capability, xtoys):
            self.capabilities.register(capability)

        self.tool_executor = ToolExecutor(self.capabilities)
        self.event_loop = EventLoop(
            brain=self.brain,
            capabilities=self.capabilities,
            memory=self.memory,
            tool_executor=self.tool_executor,
            config=config,
            role_prompt=self.role.system_prompt,
            session_logger=self.session_logger,
        )

    async def initialize(self) -> None:
        healthcheck, speech_warmup = await asyncio.gather(
            self.brain.healthcheck(),
            self.speech.warmup(),
            return_exceptions=True,
        )
        if isinstance(healthcheck, Exception):
            available, details = False, str(healthcheck)
        else:
            available, details = healthcheck
        if isinstance(speech_warmup, Exception):
            console.print(f"[yellow]Не удалось заранее загрузить Speech: {speech_warmup}[/yellow]")
        if self.session_logger.enabled:
            console.print(f"[dim]Журнал сессии: {self.session_logger.log_path}[/dim]")
        if available:
            console.print(f"[green]LLM API доступен:[/green] {details}")
        else:
            console.print(
                "[yellow]LM Studio API пока недоступен.[/yellow] "
                "Браузер, XToys и поиск продолжат работать по прямым командам.\n"
                f"[dim]{details}[/dim]"
            )

    async def shutdown(self) -> None:
        await self.event_loop.shutdown()
        await self.browser_session.close()

    async def run(self, command: Optional[str] = None):
        if command:
            return await self.event_loop.run_cycle(user_input=command)
        return await self.event_loop.run_interactive()

    def get_state(self):
        return self.event_loop.state
