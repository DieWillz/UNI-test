"""Event Loop - core autonomous cycle: Observe → Think → Speak → Act → Verify"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from ..brain import Brain
from ..state import AgentState
from ..working_memory import WorkingMemory
from ..capabilities.registry import CapabilityRegistry
from ..tools import ToolExecutor, get_tool_schemas
from ..roles.loader import RoleLoader, Role
from ..config import Config


class CycleResult(Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    ERROR = "error"
    WAITING_INPUT = "waiting_input"


@dataclass
class ExecutionStep:
    tool_name: str
    args: dict
    result: dict | None = None
    verified: bool = False
    error: str | None = None


@dataclass
class CycleContext:
    user_input: str | None = None
    screen_base64: str | None = None
    steps: list[ExecutionStep] = field(default_factory=list)
    cycle_count: int = 0
    max_cycles: int = 50


class EventLoop:
    def __init__(
        self,
        brain: Brain,
        capabilities: CapabilityRegistry,
        memory: WorkingMemory,
        config: Config,
        role: Role,
    ):
        self.brain = brain
        self.capabilities = capabilities
        self.memory = memory
        self.config = config
        self.role = role

        self.tool_executor = ToolExecutor(capabilities)
        self.state = AgentState.IDLE
        self.context = CycleContext()

    def set_state(self, new_state: AgentState) -> None:
        from ..state import can_transition
        if can_transition(self.state, new_state):
            old_state = self.state
            self.state = new_state
            if self.config.agent.state_logging:
                print(f"🔄 State: {old_state.value} → {new_state.value}")
        else:
            raise ValueError(f"Invalid state transition: {self.state} → {new_state}")

    async def run_cycle(self, user_input: str | None = None) -> CycleResult:
        """Execute one full cycle: Observe → Think → Speak → Act → Verify"""
        self.context.user_input = user_input
        self.context.cycle_count += 1

        if self.context.cycle_count > self.context.max_cycles:
            return CycleResult.ERROR

        try:
            # 1. OBSERVE
            self.set_state(AgentState.THINKING)
            observation = await self._observe()

            # 2. THINK
            response = await self._think(observation)

            # 3. SPEAK (if has text)
            if response.text:
                self.set_state(AgentState.SPEAKING)
                await self._speak(response.text)

            # 4. ACT (execute tool calls)
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    self.set_state(AgentState.EXECUTING)
                    result = await self._act(tool_call)

                    # 5. VERIFY
                    verified = await self._verify(tool_call, result)
                    if not verified:
                        # Replan on failure
                        self.memory.set("last_error", f"Verification failed: {tool_call.name}")
                        continue

            # Check if task complete
            if self._is_task_complete(response):
                return CycleResult.COMPLETE

            return CycleResult.CONTINUE

        except Exception as e:
            self.set_state(AgentState.ERROR)
            await self._speak(f"Ошибка: {str(e)}")
            return CycleResult.ERROR

    async def _observe(self) -> dict:
        """Capture screen and get memory context."""
        observation = {}

        # Capture screen
        computer = self.capabilities.get("computer")
        if computer:
            screen_result = await computer.execute("screenshot_region", {})
            if screen_result.get("success"):
                observation["screen_base64"] = screen_result.get("image_base64")
                self.context.screen_base64 = screen_result.get("image_base64")

        # Get memory context
        observation["memory_context"] = self.memory.get_context()
        observation["user_input"] = self.context.user_input

        return observation

    def _build_prompt(self, observation: dict) -> list[dict]:
        """Build prompt for LLM."""
        messages = [
            {"role": "system", "content": self.role.system_prompt},
        ]

        # Add context
        context_parts = []
        if observation.get("memory_context"):
            context_parts.append(f"Память:\n{observation['memory_context']}")
        if observation.get("user_input"):
            context_parts.append(f"Команда пользователя: {observation['user_input']}")

        if context_parts:
            messages.append({"role": "user", "content": "\n\n".join(context_parts)})

        # Add image if available
        if observation.get("screen_base64"):
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Текущий экран:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{observation['screen_base64']}"}},
                ],
            })

        return messages

    async def _think(self, observation: dict):
        """Send prompt to LLM and get response."""
        messages = self._build_prompt(observation)
        tools = get_tool_schemas()
        response = await self.brain.chat(messages, tools)
        return response

    async def _speak(self, text: str) -> None:
        """Speak text via TTS."""
        speech = self.capabilities.get("speech")
        if speech:
            await speech.execute("speak", {"text": text})

    async def _act(self, tool_call) -> dict:
        """Execute tool call."""
        result = await self.tool_executor.execute(tool_call.name, tool_call.arguments)
        step = ExecutionStep(tool_name=tool_call.name, args=tool_call.arguments, result=result)
        self.context.steps.append(step)
        return result

    async def _verify(self, tool_call, result: dict) -> bool:
        """Verify action result."""
        if not self.config.agent.verification_enabled:
            return True

        if not result.get("success"):
            return False

        # For visual actions, verify with vision
        vision = self.capabilities.get("vision")
        computer = self.capabilities.get("computer")
        if vision and computer and tool_call.name in ["click", "type", "press", "click_selector", "type_selector"]:
            # Take new screenshot and verify
            screen_result = await computer.execute("screenshot_region", {})
            if screen_result.get("success"):
                verify_prompt = f"Проверил, успешно ли выполнено действие: {tool_call.name} с аргументами {tool_call.arguments}. Верни JSON: {{\"success\": bool, \"reason\": \"...\"}}"
                verify_result = await vision.execute("analyze_screen", {
                    "image_base64": screen_result["image_base64"],
                    "prompt": verify_prompt,
                })
                if verify_result.get("success"):
                    try:
                        import json
                        parsed = json.loads(verify_result["analysis"])
                        return parsed.get("success", True)
                    except:
                        pass
        return True

    def _is_task_complete(self, response) -> bool:
        """Check if task is complete."""
        # Simple heuristic: no tool calls and text indicates completion
        if not response.tool_calls and response.text:
            completion_keywords = ["готово", "выполнено", "завершено", "done", "complete"]
            return any(kw in response.text.lower() for kw in completion_keywords)
        return False

    async def run_continuous(self, initial_input: str | None = None, max_cycles: int = 50) -> None:
        """Run continuous cycles until max_cycles or completion."""
        user_input = initial_input
        for _ in range(max_cycles):
            result = await self.run_cycle(user_input)
            if result == CycleResult.COMPLETE:
                break
            elif result == CycleResult.ERROR:
                break
            user_input = None  # Only use initial input once
            await asyncio.sleep(self.config.agent.cycle_interval)