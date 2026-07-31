"""Agent Class - Main orchestrator"""

import asyncio
import signal
from pathlib import Path
from typing import Optional

from .brain import Brain
from .capabilities.registry import CapabilityRegistry
from .capabilities.speech import SpeechCapability
from .capabilities.computer import ComputerCapability
from .capabilities.browser import BrowserCapability
from .capabilities.vision import VisionCapability
from .capabilities.memory import MemoryCapability
from .config import Config, load_config
from .event_loop import EventLoop
from .state import AgentState
from .tools.executors import ToolExecutor
from .working_memory import WorkingMemory
from .roles.loader import RoleLoader


class Agent:
    def __init__(self, config: Optional[Config] = None, config_path: Optional[str] = None):
        self.config = config or load_config(config_path)
        self._setup_complete = False

        # Core components
        self.brain: Optional[Brain] = None
        self.capabilities: Optional[CapabilityRegistry] = None
        self.memory: Optional[WorkingMemory] = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.event_loop: Optional[EventLoop] = None
        self.role_loader: Optional[RoleLoader] = None
        self.role = None

        # State
        self.state = AgentState.IDLE
        self._running = False

    async def initialize(self) -> None:
        """Initialize all components."""
        print("🤖 UNI initializing...")

        # 1. Brain
        self.brain = Brain(self.config)
        print("  ✅ Brain connected to LM Studio")

        # 2. Working Memory
        memory_path = Path(self.config.capabilities.memory.path)
        self.memory = WorkingMemory(memory_path)
        print(f"  ✅ Working Memory loaded ({len(self.memory.list_keys())} keys)")

        # 3. Capabilities
        self.capabilities = CapabilityRegistry()

        # Speech
        speech = SpeechCapability(
            stt_model=self.config.capabilities.speech.stt_model,
            tts_voice=self.config.capabilities.speech.tts_voice,
            sample_rate=self.config.capabilities.speech.sample_rate,
        )
        self.capabilities.register(speech)

        # Computer
        computer = ComputerCapability(
            use_uia=self.config.capabilities.computer.use_uia,
            failsafe=self.config.capabilities.computer.failsafe,
        )
        self.capabilities.register(computer)

        # Browser
        browser = BrowserCapability(
            headless=self.config.capabilities.browser.headless,
            viewport_width=self.config.capabilities.browser.viewport_width,
            viewport_height=self.config.capabilities.browser.viewport_height,
            timeout=self.config.capabilities.browser.timeout,
        )
        self.capabilities.register(browser)

        # Vision
        vision = VisionCapability(self.brain, self.config)
        self.capabilities.register(vision)

        # Memory
        memory_cap = MemoryCapability(self.memory)
        self.capabilities.register(memory_cap)

        # Initialize all capabilities
        await self.capabilities.initialize_all()
        print("  ✅ All capabilities initialized")

        # 4. Tool Executor
        self.tool_executor = ToolExecutor(self.capabilities)
        print("  ✅ Tool Executor ready")

        # 5. Role Loader
        self.role_loader = RoleLoader()
        self.role = self.role_loader.load(self.config.agent.default_role)
        print(f"  ✅ Role loaded: {self.config.agent.default_role}")

        # 6. Event Loop
        self.event_loop = EventLoop(
            brain=self.brain,
            capabilities=self.capabilities,
            memory=self.memory,
            config=self.config,
            role=self.role,
        )
        print("  ✅ Event Loop ready")

        self._setup_complete = True
        print("🚀 UNI ready!")

    async def run(self, initial_command: Optional[str] = None) -> None:
        """Run the agent."""
        if not self._setup_complete:
            await self.initialize()

        self._running = True
        self.state = AgentState.IDLE

        # Speak greeting
        await self._speak("Привет! Я Юни, твой локальный AI-ассистент. Чем могу помочь?")

        # Handle signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Run event loop continuously
        await self.event_loop.run_continuous(initial_command)

    async def _speak(self, text: str) -> None:
        """Speak text."""
        if self.capabilities:
            speech = self.capabilities.get("speech")
            if speech:
                await speech.execute("speak", {"text": text})

    async def process_command(self, command: str) -> None:
        """Process a single command."""
        if self.event_loop:
            await self.event_loop.run_cycle(command)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        print("\n🛑 Shutting down UNI...")
        self._running = False
        
        if self.capabilities:
            await self.capabilities.shutdown_all()
        
        if self.memory:
            self.memory.persist()
        
        print("👋 UNI stopped.")