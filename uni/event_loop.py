"""Event Loop - core autonomous cycle: Observe → Think → Speak → Act → Verify
With Planner integration for multi-step task execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from .brain import Brain
from .state import AgentState
from .working_memory import WorkingMemory
from .capabilities.registry import CapabilityRegistry
from .tools import ToolExecutor, get_tool_schemas
from .roles.loader import Role
from .config import Config
from .planner import PlannerImpl
from .planner_interface import Action, ActionResult, Task, TaskQueueImpl, TaskStatus, ErrorType


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
    current_goal: str | None = None
    task_queue: TaskQueueImpl = field(default_factory=TaskQueueImpl)
    action_history: list[ActionResult] = field(default_factory=list)


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
        self.planner = PlannerImpl(brain, capabilities, config)
        
        self.state = AgentState.IDLE
        self.context = CycleContext()

    def set_state(self, new_state: AgentState) -> None:
        from .state import can_transition
        if can_transition(self.state, new_state):
            old_state = self.state
            self.state = new_state
            if self.config.agent.state_logging:
                print(f"🔄 State: {old_state.value} → {new_state.value}")
        else:
            raise ValueError(f"Invalid state transition: {self.state} → {new_state}")

    async def run_cycle(self, user_input: str | None = None) -> CycleResult:
        """Execute one full cycle with Planner integration."""
        self.context.user_input = user_input
        self.context.cycle_count += 1

        if self.context.cycle_count > self.context.max_cycles:
            return CycleResult.ERROR

        try:
            # 1. OBSERVE
            self.set_state(AgentState.THINKING)
            observation = await self._observe()

            # 2. PLAN (if new goal or queue empty)
            if user_input or self.context.task_queue.is_empty():
                if user_input:
                    self.context.current_goal = user_input
                    self.context.action_history.clear()
                
                if self.context.current_goal:
                    tasks = await self.planner.plan(self.context.current_goal, self.context.action_history)
                    for task in tasks:
                        await self.context.task_queue.push(task)

            # 3. GET NEXT TASK
            task = await self.context.task_queue.pop()
            if not task:
                # No tasks ready - check if complete
                if self.context.task_queue.is_empty():
                    if self.context.action_history:
                        # Task sequence complete
                        self.set_state(AgentState.SPEAKING)
                        await self._speak("Задача выполнена.")
                        self.context.current_goal = None
                        return CycleResult.COMPLETE
                    return CycleResult.WAITING_INPUT
                # Dependencies not met yet, wait
                await asyncio.sleep(0.5)
                return CycleResult.CONTINUE

            # 4. EXECUTE TASK
            self.set_state(AgentState.EXECUTING)
            action_result = await self._execute_task(task)

            # 5. VERIFY & HANDLE RESULT
            verified = await self._verify_action(task, action_result)
            
            # Record in history
            action_result_data = ActionResult(
                action=task.action,
                status="success" if (action_result.get("success") and verified) else "failure",
                data=action_result.get("data"),
                error=action_result.get("error") if not (action_result.get("success") and verified) else None,
                error_type=ErrorType.TRANSIENT,
            )
            self.context.action_history.append(action_result_data)

            if not (action_result.get("success") and verified):
                # REPLAN on failure
                if task.retry_count < task.max_retries:
                    await self.context.task_queue.requeue(task)
                    self.memory.set("last_error", f"Verification failed: {task.action.name}")
                else:
                    # Max retries exceeded - replan
                    try:
                        new_tasks = await self.planner.replan(
                            self.context.current_goal or "", task, self.context.action_history
                        )
                        for t in new_tasks:
                            await self.context.task_queue.push(t)
                    except RuntimeError:
                        await self._speak("Не удалось выполнить задачу после нескольких попыток.")
                        return CycleResult.ERROR

            # Check if all tasks complete
            if self.context.task_queue.is_empty() and self.context.current_goal:
                self.set_state(AgentState.SPEAKING)
                await self._speak("Задача выполнена.")
                self.context.current_goal = None
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

    async def _execute_task(self, task: Task) -> dict:
        """Execute a single task (tool call)."""
        tool_name = task.action.name
        args = task.action.params
        
        print(f"🎯 Executing: {tool_name}({args})")
        
        result = await self.tool_executor.execute(tool_name, args)
        
        step = ExecutionStep(tool_name=tool_name, args=args, result=result)
        self.context.steps.append(step)
        
        # Small delay between actions
        await asyncio.sleep(0.1)
        
        return result

    async def _verify_action(self, task: Task, result: dict) -> bool:
        """Verify action result using vision."""
        if not self.config.agent.verification_enabled:
            return True

        if not result.get("success"):
            return False

        # For visual actions, verify with vision
        vision = self.capabilities.get("vision")
        computer = self.capabilities.get("computer")
        
        visual_actions = ["click", "type", "press", "click_selector", "type_selector", "navigate"]
        if vision and computer and task.action.name in visual_actions:
            screen_result = await computer.execute("screenshot_region", {})
            if screen_result.get("success"):
                verify_prompt = f"Проверил, успешно ли выполнено действие: {task.action.name} с аргументами {task.action.params}. Верни JSON: {{\"success\": bool, \"reason\": \"...\"}}"
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

    async def _speak(self, text: str) -> None:
        """Speak text via TTS."""
        speech = self.capabilities.get("speech")
        if speech:
            await speech.execute("speak", {"text": text})

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