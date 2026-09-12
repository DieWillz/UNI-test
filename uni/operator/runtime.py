from __future__ import annotations

import asyncio
from uuid import uuid4

from uni.contracts import TaskOutcome, TaskStatus, Verification

from .action_registry import DEFAULT_ACTION_REGISTRY
from .browser_provider import BrowserProvider
from .executor import MissionExecutor
from .file_provider import FileProvider
from .input_broker import InputBroker, InputStopped
from .execution_policy import ExecutionPolicy
from .visible_actions import VisibleDesktopDriver
from .progress import EventSink, ProgressEvent, ProgressState, emit
from .models import MissionPlan, PlanStep, Postcondition
from .perception import PerceptionBroker
from .permissions import MissionPermissions
from .planner import MissionPlanner
from .windows_provider import WindowsProvider


class OperatorRuntime:
    def __init__(self, *, brain, browser_session, computer, vision, tool_executor,
                 session_logger=None, execution_policy=None, visible_driver=None,
                 event_sink: EventSink | None = None, planner_context_limit: int = 5120,
                 planner_output_tokens: int = 900) -> None:
        self.brain = brain
        self.session_logger = session_logger
        self.input_broker = InputBroker()
        self.browser = BrowserProvider(browser_session)
        self.windows = WindowsProvider(computer)
        self.files = FileProvider()
        self.perception = PerceptionBroker(self.browser, self.windows, vision=vision)
        self.windows.fallback_resolver = self.perception.resolve_desktop
        self.planner = MissionPlanner(brain, DEFAULT_ACTION_REGISTRY, session_logger=session_logger,
                                      model_context_limit=planner_context_limit,
                                      reserved_output_tokens=planner_output_tokens)
        self.event_sink = event_sink
        self.executor = MissionExecutor(
            planner=self.planner,
            perception=self.perception,
            tool_executor=tool_executor,
            registry=DEFAULT_ACTION_REGISTRY,
            browser_provider=self.browser,
            windows_provider=self.windows,
            file_provider=self.files,
            input_broker=self.input_broker,
            execution_policy=execution_policy or ExecutionPolicy(),
            visible_driver=visible_driver or VisibleDesktopDriver(computer),
            event_sink=event_sink,
        )
        self._mission_lock = asyncio.Lock()
        self.current_goal = ""

    def stop(self) -> None:
        self.input_broker.stop()

    def resume(self) -> bool:
        if self._mission_lock.locked():
            return False
        self.input_broker.reset_stop()
        return True

    async def inspect(self):
        return await self.perception.observe()

    async def run_action(self, name: str, params: dict, *,
                         permissions: MissionPermissions | None = None,
                         postcondition: Postcondition | None = None):
        """Route a deterministic legacy intent through the existing executor.

        No model replanning, no second executor, and no implicit STOP reset.
        Unknown postconditions remain NOT_VERIFIED, never inferred from ACKs.
        """
        spec = self.executor.registry.get(name)
        if postcondition is None and spec.name == "browser.navigate":
            postcondition = Postcondition(kind="browser.url_equals", params={"value": params.get("url")})
        goal = f"{spec.name}"
        plan = MissionPlan(goal=goal, steps=[PlanStep(
            id="legacy-action", action=spec.name, params=dict(params),
            postcondition=postcondition, retry_budget=0,
        )])
        return await self.run(goal, permissions=permissions, plan=plan, resume_stopped=False)

    async def run(self, goal: str, *, permissions: MissionPermissions | None = None,
                  plan: MissionPlan | None = None, resume_stopped: bool = False) -> TaskOutcome:
        # The compatibility argument no longer clears STOP. Only explicit resume()
        # when idle starts a new generation; queued work always keeps its epoch.
        generation = self.input_broker.generation
        mission_id = f"mission-{uuid4().hex[:12]}"
        emit(self.event_sink, ProgressEvent(mission_id, ProgressState.ACKNOWLEDGED))
        async with self._mission_lock:
            try:
                self.input_broker.ensure_active(generation)
            except InputStopped:
                emit(self.event_sink, ProgressEvent(mission_id, ProgressState.STOPPED))
                return TaskOutcome.finalize(command=goal, message="Mission interrupted by STOP",
                    verification=Verification(reason="mission_generation_invalidated"),
                    failure_status=TaskStatus.INTERRUPTED)
            self.current_goal = goal
            try:
                return await self.executor.run(goal, permissions=permissions, plan=plan,
                                               mission_id=mission_id, generation=generation)
            finally:
                self.current_goal = ""
