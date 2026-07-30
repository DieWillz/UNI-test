"""
uni.planner — Planner implementation (Build 12)
Author: DeepSeek / Nemotron integration
Implements: planner_interface.py contract
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from .brain import Brain
from .planner_interface import (
    Action,
    ActionResult,
    ErrorType,
    Planner,
    Task,
    TaskQueue,
    TaskStatus,
    classify_error,
    retry_delay,
    DEFAULT_PRIORITY_MAP,
    DEFAULT_RETRY_OVERRIDES,
)
from .capabilities.registry import CapabilityRegistry
from .config import Config
from .tools.results import ToolResult


class TaskQueueImpl(TaskQueue):
    """In-memory priority queue with dependency resolution."""

    def __init__(self):
        self._tasks: list[Task] = []
        self._completed: set[str] = set()
        self._running: set[str] = set()

    async def push(self, task: Task) -> None:
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: (t.priority, t.retry_count))

    async def pop(self) -> Task | None:
        # Find first task whose dependencies are satisfied and not running
        for i, task in enumerate(self._tasks):
            if task.status == TaskStatus.PENDING:
                deps_met = all(dep in self._completed for dep in task.depends_on)
                if deps_met:
                    task.status = TaskStatus.RUNNING
                    self._running.add(task.id)
                    return self._tasks.pop(i)
        return None

    async def mark_completed(self, task_id: str) -> None:
        self._completed.add(task_id)
        self._running.discard(task_id)

    async def requeue(self, task: Task, increment_retry: bool = True) -> None:
        if increment_retry:
            task.retry_count += 1
        task.status = TaskStatus.PENDING
        self._running.discard(task.id)
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: (t.priority, t.retry_count))

    async def clear_pending(self) -> None:
        self._tasks = [t for t in self._tasks if t.status == TaskStatus.RUNNING]

    def is_empty(self) -> bool:
        return all(t.status != TaskStatus.PENDING for t in self._tasks)


class PlannerImpl(Planner):
    """LLM-based planner with deterministic retry/replan logic."""

    def __init__(self, brain: Brain, capability_registry: CapabilityRegistry, config: Config):
        self.brain = brain
        self.registry = capability_registry
        self.config = config
        self.max_replans = config.agent.max_retries
        self.current_replans = 0

    def _build_capability_descriptions(self) -> str:
        """Generate capability descriptions for LLM prompt."""
        caps = []
        for name in self.registry.list():
            cap = self.registry.get(name)
            if cap:
                tools = cap.list_tools()
                for tool in tools:
                    caps.append(f"- {tool.name}: {tool.description}")
        return "\n".join(caps)

    def _build_plan_prompt(self, goal: str, context: list[ActionResult]) -> tuple[str, str]:
        """Build system and user prompts for planning."""
        system = f"""Ты — UNI Planner. Разбей цель пользователя на последовательность действий.

ДОСТУПНЫЕ ДЕЙСТВИЯ (capability.action):
{self._build_capability_descriptions()}

ПРАВИЛА:
1. Возвращай ТОЛЬКО JSON-массив действий, каждый с полями:
   {{"name": "capability.action", "params": {{...}}, "priority": 0|1|2, "depends_on": []}}
2. priority: 0=критично (запуск браузера), 1=нормально, 2=фон
3. depends_on — ID предыдущих действий, от которых зависит это
4. Максимум 10 действий на план
5. Последнее действие должно проверять результат (vision.verify или memory.get)
"""
        user = f"Цель: {goal}\n\nКонтекст (предыдущие результаты):\n"
        if context:
            for r in context[-5:]:
                user += f"- {r.action.name}: {'успех' if r.status == 'success' else 'ошибка: ' + (r.error or 'unknown')}\n"
        else:
            user += "(пусто)\n"
        return system, user

    async def plan(self, goal: str, context: list[ActionResult]) -> list[Task]:
        system, user = self._build_plan_prompt(goal, context)
        
        response = await self.brain.simple_chat(f"{system}\n\n{user}")
        
        try:
            # Extract JSON from response
            start = response.find('[')
            end = response.rfind(']') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array in response")
            plan_json = response[start:end]
            actions_data = json.loads(plan_json)
        except Exception as e:
            # Fallback: simple single-action plan
            actions_data = [{"name": "computer.screenshot_region", "params": {}, "priority": 1}]

        tasks = []
        for i, action_data in enumerate(actions_data):
            task_id = str(uuid.uuid4())[:8]
            task = Task(
                id=task_id,
                action=Action(name=action_data["name"], params=action_data.get("params", {})),
                priority=action_data.get("priority", 1),
                depends_on=action_data.get("depends_on", []),
                max_retries=DEFAULT_RETRY_OVERRIDES.get(action_data["name"], 3),
            )
            tasks.append(task)
        
        return tasks

    async def replan(self, goal: str, failed_task: Task, history: list[ActionResult]) -> list[Task]:
        """Re-plan after failure with failure context."""
        self.current_replans += 1
        if self.current_replans > self.max_replans:
            raise RuntimeError(f"Max replans ({self.max_replans}) exceeded")

        system = f"""Ты — UNI Planner. Предыдущий план провалился.

ОШИБКА: {failed_task.action.name} → {history[-1].error if history else 'unknown'}
Тип ошибки: {classify_error(history[-1].error if history else '').value}

Предложи ИСПРАВЛЕННЫЙ план. Используй те же доступные действия.
Верни ТОЛЬКО JSON-массив."""
        
        user = f"Цель: {goal}\nИстория: {len(history)} действий"
        
        response = await self.brain.simple_chat(f"{system}\n\n{user}")
        
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            plan_json = response[start:end]
            actions_data = json.loads(plan_json)
        except Exception:
            # Minimal fallback
            actions_data = [{"name": "computer.screenshot_region", "params": {}, "priority": 1}]

        tasks = []
        for i, action_data in enumerate(actions_data):
            task_id = str(uuid.uuid4())[:8]
            task = Task(
                id=task_id,
                action=Action(name=action_data["name"], params=action_data.get("params", {})),
                priority=action_data.get("priority", 1),
                depends_on=action_data.get("depends_on", []),
                max_retries=DEFAULT_RETRY_OVERRIDES.get(action_data["name"], 3),
            )
            tasks.append(task)
        
        return tasks