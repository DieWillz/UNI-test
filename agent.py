from typing import Optional
from uni.config import Config
from uni.brain import Brain
from uni.working_memory import WorkingMemory
from uni.capabilities.registry import CapabilityRegistry
from uni.capabilities.speech import SpeechCapability
from uni.capabilities.computer import ComputerCapability
from uni.capabilities.browser import BrowserCapability
from uni.capabilities.vision import VisionCapability
from uni.capabilities.memory import MemoryCapability
from uni.capabilities.xtoys import XToysCapability
from uni.tools import ToolExecutor
from uni.event_loop import EventLoop
from uni.state import AgentState

class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.brain = Brain(config.brain)
        self.memory = WorkingMemory(config.memory.path)

        speech = SpeechCapability(
            stt_model=config.capabilities.speech.stt_model,
            tts_voice=config.capabilities.speech.tts_voice,
            sample_rate=config.capabilities.speech.sample_rate,
        )
        computer = ComputerCapability(
            use_uia=config.capabilities.computer.use_uia,
            failsafe=config.capabilities.computer.failsafe,
        )
        browser = BrowserCapability(
            headless=config.capabilities.browser.headless,
            viewport_width=config.capabilities.browser.viewport_width,
            viewport_height=config.capabilities.browser.viewport_height,
        )
        vision = VisionCapability(self.brain, config)
        memory_cap = MemoryCapability(self.memory)
        xtoys = XToysCapability(browser, vision, url="https://xtoys.app")

        self.capabilities = CapabilityRegistry()
        self.capabilities.register(speech)
        self.capabilities.register(computer)
        self.capabilities.register(browser)
        self.capabilities.register(vision)
        self.capabilities.register(memory_cap)
        self.capabilities.register(xtoys)

        self.tool_executor = ToolExecutor(self.capabilities)
        self.event_loop = EventLoop(
            brain=self.brain,
            capabilities=self.capabilities,
            memory=self.memory,
            tool_executor=self.tool_executor,
            config=config,
        )
        self.state = AgentState.IDLE

    async def run(self, command: Optional[str] = None):
        if command:
            await self.event_loop.run_cycle(user_input=command)
        else:
            await self.event_loop.run_interactive()

    def get_state(self):
        return self.state
