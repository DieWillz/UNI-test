"""uni.agent — точка сборки агента. Полная реализация."""

from __future__ import annotations

import asyncio
from uni.config import Config
from uni.brain import Brain
from uni.working_memory import WorkingMemory
from uni.capabilities.registry import CapabilityRegistry
from uni.capabilities.speech import SpeechCapability
from uni.capabilities.computer import ComputerCapability
from uni.capabilities.browser import BrowserCapability
from uni.capabilities.vision import VisionCapability
from uni.capabilities.memory import MemoryCapability
from uni.tools.executors import ToolExecutor
from uni.roles.loader import RoleLoader
from uni.event_loop import EventLoop
from uni.state import AgentState


class Agent:
    """Точка сборки агента. Полная реализация."""

    def __init__(self, config: Config) -> None:
        self.config = config

        # Brain
        self.brain = Brain(config)

        # Memory
        self.memory = WorkingMemory(config.memory.path)

        # Capabilities
        self.capabilities = CapabilityRegistry()
        self.capabilities.register(SpeechCapability(
            stt_model=config.capabilities["speech"].stt_model,
            tts_voice=config.capabilities["speech"].tts_voice,
            sample_rate=config.capabilities["speech"].sample_rate,
        ))
        self.capabilities.register(ComputerCapability(
            use_uia=config.capabilities["computer"].use_uia,
            failsafe=config.capabilities["computer"].failsafe,
        ))
        self.capabilities.register(BrowserCapability(
            headless=config.capabilities["browser"].headless,
            viewport_width=config.capabilities["browser"].viewport["width"],
            viewport_height=config.capabilities["browser"].viewport["height"],
            timeout=config.capabilities["browser"].timeout,
        ))
        self.capabilities.register(VisionCapability(self.brain, config))
        self.capabilities.register(MemoryCapability(self.memory))

        # Tool executor + Event loop
        self.tool_executor = ToolExecutor(self.capabilities)
        self.role_loader = RoleLoader()
        self.role = self.role_loader.load(config.agent.default_role)

        self.event_loop = EventLoop(
            brain=self.brain,
            capabilities=self.capabilities,
            memory=self.memory,
            config=config,
            role=self.role,
        )

    async def initialize(self) -> None:
        await self.capabilities.initialize_all()

    async def run(self, initial_command: str | None = None) -> None:
        """Запускает бесконечный цикл агента."""
        await self.initialize()
        await self.event_loop.run_continuous(initial_command)

    async def shutdown(self) -> None:
        await self.capabilities.shutdown_all()
        if self.memory:
            self.memory.persist()