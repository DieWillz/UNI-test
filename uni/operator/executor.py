from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, TypeVar
from uuid import uuid4

from uni.contracts import (Action, ActionResult, Evidence, Observation, TaskOutcome,
                           TaskStatus, ToolResult, Verification, VerificationStatus)
from uni.tools.executors import ToolExecutor
from .action_registry import ActionSpec, DEFAULT_ACTION_REGISTRY
from .execution_policy import ExecutionMethod, ExecutionPolicy
from .file_provider import FileProvider
from .input_broker import InputBroker, InputStopped
from .models import MissionPlan, PlanStep, SceneSnapshot, TargetSpec, UIElement
from .permissions import MissionPermissions, PermissionDenied, PermissionGate
from .progress import EventSink, ProgressEvent, ProgressState, emit
from .recovery import RecoveryEngine, RecoveryStrategy
from .targeting import TargetAmbiguous, TargetNotFound
from .verifier import PostconditionVerifier
from .visible_actions import VisibleTarget

T = TypeVar("T")


@dataclass
class StepExecution:
    completed: bool
    scene: SceneSnapshot
    action_result: ActionResult | None = None
    verification: Verification | None = None
    error: str = ""
    status: TaskStatus = TaskStatus.NOT_VERIFIED
    attempts: list[ActionResult] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    safe_to_replan: bool = False


class MissionExecutor:
    def __init__(self, *, planner, perception, tool_executor,
                 registry=DEFAULT_ACTION_REGISTRY, browser_provider=None,
                 windows_provider=None, file_provider=None, input_broker=None,
                 permission_gate=None, recovery=None, verifier=None,
                 execution_policy: ExecutionPolicy | None = None, visible_driver=None,
                 event_sink: EventSink | None = None) -> None:
        self.planner, self.perception, self.tool_executor = planner, perception, tool_executor
        self.registry = registry
        self.browser_provider, self.windows_provider = browser_provider, windows_provider
        self.file_provider = file_provider or FileProvider()
        self.input_broker = input_broker or InputBroker()
        self.permission_gate = permission_gate or PermissionGate()
        self.recovery = recovery or RecoveryEngine()
        self.verifier = verifier or PostconditionVerifier(file_provider=self.file_provider)
        self.execution_policy = execution_policy or ExecutionPolicy()
        self.visible_driver = visible_driver
        self.event_sink = event_sink

    def _event(self, mission_id: str, state: ProgressState, *, step: PlanStep | None = None,
               action_id: str = "", detail: str = "", plan: MissionPlan | None = None) -> None:
        emit(self.event_sink, ProgressEvent(mission_id, state, step.id if step else "",
             action_id, detail, tuple((s.id, s.action) for s in plan.steps) if plan else ()))

    @staticmethod
    def _observation(scene: SceneSnapshot, action_id: str = "") -> Observation:
        return Observation(source="operator.scene", summary="operator environmental observation",
            timestamp=scene.timestamp, confidence=0.7 if scene.errors else 1.0,
            data={"snapshot_id": scene.snapshot_id, "action_id": action_id,
                  "active_window": scene.active_window, "browser": scene.browser,
                  "element_count": len(scene.elements), "errors": scene.errors})

    async def _dispatch(self, step: PlanStep, spec: ActionSpec) -> ToolResult | dict[str, Any]:
        name = spec.name
        if name == "operator.observe":
            return (await self.perception.observe()).model_dump(mode="json")
        if name == "operator.wait":
            seconds = max(0.0, min(float(step.params.get("seconds", 0.25)), 30.0))
            await asyncio.sleep(seconds)
            return {"seconds": seconds}
        if name == "browser.navigate":
            return await self.browser_provider.act("navigate", **step.params)
        if name == "browser.current_tab":
            return (await self.browser_provider.inspect()).browser
        if name.startswith("browser."):
            return ToolResult(success=False, message="browser_action_requires_canonical_provider")
        if name.startswith("operator.browser."):
            if self.browser_provider is None:
                return ToolResult(success=False, message="browser_provider_unavailable")
            action = name.removeprefix("operator.browser.")
            try:
                return await self.browser_provider.act(action, target=step.target, **step.params)
            except Exception as exc:
                return ToolResult(success=False, message=str(exc), error=type(exc).__name__)
        if name.startswith("operator.desktop."):
            if self.windows_provider is None:
                return ToolResult(success=False, message="windows_provider_unavailable")
            action = name.removeprefix("operator.desktop.")
            return await self.windows_provider.act(action, target=step.target, **step.params)
        if name.startswith("operator.file."):
            action = name.removeprefix("operator.file.")
            try:
                return await self.file_provider.act(action, **step.params)
            except Exception as exc:
                return ToolResult(success=False, message=str(exc), error=type(exc).__name__)
        return await self.tool_executor.execute(name, step.params)

    async def _await_interruptibly(self, awaitable: Awaitable[T], generation: int | None = None) -> T:
        epoch = self.input_broker.generation if generation is None else generation
        work = asyncio.ensure_future(awaitable)
        stop = asyncio.create_task(self.input_broker.wait_stopped())
        try:
            self.input_broker.ensure_active(epoch)
            done, _ = await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
            if stop in done:
                raise InputStopped("STOP_REQUESTED")
            result = await work
            self.input_broker.ensure_active(epoch)
            return result
        finally:
            for task in (work, stop):
                if not task.done():
                    task.cancel()
            # Drain cancelled tasks: a late callback cannot start a new plan step.
            await asyncio.gather(work, stop, return_exceptions=True)

    def _validate_plan(self, plan: MissionPlan) -> None:
        remaining = {step.id: set(step.dependencies) for step in plan.steps}
        while remaining:
            ready = {key for key, dependencies in remaining.items() if not dependencies}
            if not ready:
                raise ValueError("invalid_plan_dependencies")
            remaining = {key: dependencies - ready for key, dependencies in remaining.items() if key not in ready}
        for step in plan.steps:
            spec = self.registry.get(step.action)
            if not ToolExecutor.action_allowed(spec.name):
                raise ValueError("action_blocked_by_mode")
            if set(step.params) - set(spec.parameters) or any(key not in step.params for key in spec.required):
                raise ValueError(f"invalid_action_parameters: {step.id}")
            if spec.requires_target and step.target is None:
                raise ValueError(f"target_required: {step.id}")
            if spec.side_effect and step.postcondition is None:
                raise ValueError(f"side_effect_has_no_postcondition: {step.id}")
            if step.target is not None and step.target.ref:
                raise ValueError(f"TARGET_STALE: plan requires semantic target, not cached ref: {step.id}")
            if spec.name.startswith("computer.") and any(key in step.params for key in ("x", "y")):
                raise ValueError("blind_coordinates_forbidden")

    async def _dispatch_visible(self, step: PlanStep, element: UIElement,
                                scene: SceneSnapshot, generation: int) -> ToolResult:
        assert self.visible_driver is not None and element.bbox is not None
        target = VisibleTarget(name=element.name, role=element.role,
            x=int(element.bbox.x), y=int(element.bbox.y), width=int(element.bbox.width),
            height=int(element.bbox.height), confidence=element.confidence)
        action = self.registry.get(step.action).name.removeprefix("operator.desktop.")
        if action in {"check", "uncheck"} and element.checked is (action == "check"):
            return ToolResult(success=True, message="checked state already observed")
        self.input_broker.ensure_active(generation)
        if action == "fill":
            # Each keyboard stage reobserves focus. No blind typing after a click.
            async def focus_guard() -> bool:
                self.input_broker.ensure_active(generation)
                return await self.windows_provider.focus_matches(
                    step.target, hwnd=scene.active_window.get("hwnd", 0))
            return await self.visible_driver.fill(target, str(step.params.get("text", "")),
                                                   focus_guard=focus_guard)
        if action == "press":
            focused = await self.visible_driver.focus(target)
            if not focused.success:
                return focused
            if not await self.windows_provider.focus_matches(
                    step.target, hwnd=scene.active_window.get("hwnd", 0)):
                return ToolResult(success=False, message="WINDOW_CHANGED: keyboard focus not observed")
            self.input_broker.ensure_active(generation)
            return await self.visible_driver.press(str(step.params.get("key", "")))
        return await self.visible_driver.click(target)

    async def _call_action(self, mission_id: str, step: PlanStep, spec: ActionSpec,
                           scene: SceneSnapshot, generation: int, attempt: int,
                           history: list[ActionResult]) -> ActionResult:
        if spec.physical_input:
            async with self.input_broker.acquire(mission_id) as lease:
                self.input_broker.check(lease)
                return await self._perform_action(mission_id, step, spec, scene,
                                                  generation, attempt, history)
        return await self._perform_action(mission_id, step, spec, scene, generation, attempt, history)

    async def _perform_action(self, mission_id: str, step: PlanStep, spec: ActionSpec,
                           scene: SceneSnapshot, generation: int, attempt: int,
                           history: list[ActionResult]) -> ActionResult:
        action = Action(name=spec.name, params=step.params)
        receipt: dict[str, Any] = {"action_id": action.id, "step_id": step.id,
            "target": step.target.model_dump(mode="json") if step.target else None,
            "before_snapshot_id": scene.snapshot_id, "dispatch_started": False}
        record = ActionResult(action=action, success=False, message="action_not_dispatched",
                              retry_count=attempt, data={"receipt": receipt})
        history.append(record)
        element = None
        try:
            self.input_broker.ensure_active(generation)
            self._event(mission_id, ProgressState.LOCATING, step=step, action_id=action.id)
            if spec.name.startswith(("operator.browser.", "browser.")):
                if self.browser_provider is None or not await self._await_interruptibly(
                        self.browser_provider.connected(), generation):
                    raise RuntimeError("BROWSER_DISCONNECTED")
            if step.target is not None:
                provider = self.browser_provider if spec.name.startswith("operator.browser.") else self.windows_provider
                if provider is not None:
                    fresh = await self._await_interruptibly(provider.inspect(), generation)
                    element = provider.resolve(step.target, fresh)
                    if not element.enabled:
                        raise TargetNotFound("target_not_found: disabled")
                    if (scene.active_window.get("hwnd") and spec.physical_input
                            and fresh.active_window.get("hwnd") != scene.active_window.get("hwnd")):
                        raise TargetNotFound("WINDOW_CHANGED")
                    scene = fresh
                    receipt["before_snapshot_id"] = scene.snapshot_id
                    self._event(mission_id, ProgressState.TARGET_RESOLVED, step=step, action_id=action.id)
            decision = self.execution_policy.decide(spec.name, element,
                scene=scene, visible_available=self.visible_driver is not None)
            receipt["method"] = decision.method.value
            async def dispatch():
                self.input_broker.ensure_active(generation)
                self._event(mission_id, ProgressState.ACTING, step=step, action_id=action.id,
                            detail=decision.reason)
                self.input_broker.ensure_active(generation)
                receipt["dispatch_started"] = True
                receipt["started_at"] = datetime.now(timezone.utc).isoformat()
                if decision.method is ExecutionMethod.VISIBLE:
                    return await self._dispatch_visible(step, element, scene, generation)
                return await self._dispatch(step, spec)
            raw = await self._await_interruptibly(dispatch(), generation)
            receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
            result = raw if isinstance(raw, ToolResult) else ToolResult(success=True, data=raw)
            record.success, record.message, record.error = result.success, result.message, result.error
            record.data = {"result": result.data, "receipt": receipt}
            return record
        except InputStopped:
            record.error, record.message = "STOP_REQUESTED", "action interrupted; effect not verified"
            record.data = {"receipt": receipt}
            raise
        except Exception as exc:
            # One provider/driver boundary. Unknown failures are uncertain effects,
            # never converted into a successful fallback or automatically replayed.
            receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
            record.message = str(exc)
            record.error = self.recovery.classify(type(exc).__name__ + ": " + str(exc)).value
            record.data = {"receipt": receipt}
            return record

    async def _verify_after(self, step: PlanStep, before: SceneSnapshot, scene: SceneSnapshot,
                            action: ActionResult, generation: int) -> Verification:
        receipt = action.data["receipt"]
        try:
            observed = datetime.fromisoformat(scene.timestamp)
            finished = datetime.fromisoformat(receipt["completed_at"])
            valid = (observed.tzinfo is not None and observed >= finished
                     and scene.snapshot_id != before.snapshot_id
                     and scene.snapshot_id != receipt["before_snapshot_id"])
        except (ValueError, TypeError, KeyError):
            valid = False
        if not valid:
            return Verification(reason="fresh_post_action_observation_missing")
        if step.postcondition is None:
            return Verification(reason="explicit_postcondition_missing")
        provider_receipt = (action.data.get("result") or {})
        if isinstance(provider_receipt, dict) and provider_receipt.get("receipt"):
            if scene.browser.get("last_action", {}).get("id") != provider_receipt["receipt"].get("id"):
                return Verification(reason="browser_action_receipt_mismatch")
        decision = await self._await_interruptibly(self.verifier.verify(step, scene=scene), generation)
        if decision.status is VerificationStatus.VERIFIED:
            # Bind independently collected evidence to the action; this is provenance,
            # not replacement evidence manufactured from tool success.
            decision = decision.model_copy(update={"evidence": [item.model_copy(update={"data": {
                "observed": item.data, "action_id": action.action.id,
                "snapshot_id": scene.snapshot_id, "target": receipt["target"],
            }}) for item in decision.evidence]})
        return decision

    async def _execute_step(self, mission_id: str, step: PlanStep, scene: SceneSnapshot,
                            permissions: MissionPermissions, generation: int,
                            replan_count: int, actions: list[ActionResult],
                            observations: list[Observation]) -> StepExecution:
        spec = self.registry.get(step.action)
        result = StepExecution(False, scene, attempts=actions, observations=observations)
        try:
            self.permission_gate.require(spec, permissions)
        except PermissionDenied as exc:
            result.error, result.status = str(exc), TaskStatus.BLOCKED
            return result
        for attempt in range(step.retry_budget + 1):
            self.input_broker.ensure_active(generation)
            self._event(mission_id, ProgressState.OBSERVING, step=step)
            before = await self._await_interruptibly(self.perception.observe(), generation)
            result.scene = before
            result.observations.append(self._observation(before))
            action = await self._call_action(mission_id, step, spec, before, generation, attempt, actions)
            result.action_result = action
            receipt = action.data["receipt"]
            if not receipt["dispatch_started"]:
                decision = self.recovery.decide(error=(action.error or "") + ": " + action.message,
                                                attempt=attempt, replan_count=replan_count)
                result.error = decision.reason
                result.safe_to_replan = decision.strategy in {RecoveryStrategy.REOBSERVE, RecoveryStrategy.REPLAN}
                if decision.strategy is RecoveryStrategy.REOBSERVE and attempt < step.retry_budget:
                    continue
                return result
            # Even failed/uncertain actions must attempt a fresh observation.
            self._event(mission_id, ProgressState.OBSERVING, step=step, action_id=action.action.id)
            scene = await self._await_interruptibly(self.perception.observe(), generation)
            result.scene = scene
            result.observations.append(self._observation(scene, action.action.id))
            if not spec.side_effect and step.postcondition is None:
                # A read can feed the next step, but cannot alone certify the goal.
                result.completed = action.success
                result.error = "" if action.success else action.message
                return result
            self._event(mission_id, ProgressState.VERIFYING, step=step, action_id=action.action.id)
            decision = await self._verify_after(step, before, scene, action, generation)
            result.verification = decision
            if action.success and decision.status is VerificationStatus.VERIFIED:
                action.verified = True
                result.completed, result.status = True, TaskStatus.VERIFIED
                return result
            result.error = decision.reason if action.success else (action.error or action.message or "ACTION_FAILED")
            # An unconfirmed click/submit/type is not automatically retried.
            return result
        result.error = "retry_budget_exhausted"
        return result

    @staticmethod
    def _requirements(steps: list[PlanStep]) -> dict[str, Any]:
        return {"remaining_postconditions": [
            {"target": step.target.model_dump(mode="json") if step.target else None,
             "postcondition": step.postcondition.model_dump(mode="json")}
            for step in steps if step.postcondition is not None]}

    async def run(self, goal: str, *, permissions: MissionPermissions | None = None,
                  plan: MissionPlan | None = None, mission_id: str | None = None,
                  generation: int | None = None) -> TaskOutcome:
        own_id = mission_id is None
        mission_id = mission_id or f"mission-{uuid4().hex[:12]}"
        epoch = self.input_broker.generation if generation is None else generation
        if own_id:
            self._event(mission_id, ProgressState.ACKNOWLEDGED)
        actions: list[ActionResult] = []
        observations: list[Observation] = []
        evidence: list[Evidence] = []
        permissions = permissions or MissionPermissions()
        def finish(reason: str, status: TaskStatus = TaskStatus.NOT_VERIFIED) -> TaskOutcome:
            self._event(mission_id, ProgressState.STOPPED if status is TaskStatus.INTERRUPTED else
                        ProgressState.BLOCKED if status is TaskStatus.BLOCKED else ProgressState.NOT_VERIFIED)
            return TaskOutcome.finalize(command=goal, message=reason, actions=actions,
                observations=observations, verification=Verification(reason=reason), failure_status=status)
        try:
            self.input_broker.ensure_active(epoch)
            self._event(mission_id, ProgressState.OBSERVING)
            scene = await self._await_interruptibly(self.perception.observe(), epoch)
            observations.append(self._observation(scene))
            if plan is None:
                self._event(mission_id, ProgressState.PLANNING)
                plan = await self._await_interruptibly(self.planner.plan(goal, scene=scene), epoch)
            self._validate_plan(plan)
            if not plan.steps:
                return finish("empty_plan")
            self._event(mission_id, ProgressState.PLAN_READY, plan=plan)
            pending = list(plan.steps)
            completed: set[str] = set()
            replan_count = 0
            while pending:
                self.input_broker.ensure_active(epoch)
                step = next((item for item in pending if set(item.dependencies) <= completed), None)
                if step is None:
                    return finish("unsatisfied_plan_dependencies", TaskStatus.BLOCKED)
                result = await self._execute_step(mission_id, step, scene, permissions, epoch, replan_count, actions, observations)
                scene = result.scene
                if not result.completed:
                    if result.safe_to_replan and replan_count < self.recovery.max_replans:
                        requirements = self._requirements(pending)
                        self._event(mission_id, ProgressState.REPLANNING, step=step, detail=result.error)
                        new_plan = await self._await_interruptibly(self.planner.plan(
                            goal, scene=scene, failure_context=result.error, requirements=requirements), epoch)
                        self._validate_plan(new_plan)
                        expected = [json.dumps(item, sort_keys=True) for item in requirements["remaining_postconditions"]]
                        provided = [json.dumps(item, sort_keys=True) for item in self._requirements(new_plan.steps)["remaining_postconditions"]]
                        for condition in expected:
                            if condition not in provided:
                                return finish("replan_changed_required_postcondition", TaskStatus.BLOCKED)
                            provided.remove(condition)
                        pending, completed = list(new_plan.steps), set()
                        replan_count += 1
                        self._event(mission_id, ProgressState.PLAN_READY, plan=new_plan)
                        continue
                    return finish(result.error, result.status)
                if result.verification is not None:
                    evidence.extend(result.verification.evidence)
                pending.remove(step)
                completed.add(step.id)
            self.input_broker.ensure_active(epoch)
            if not evidence:
                return finish("no_independent_mission_evidence")
            decision = Verification(status=VerificationStatus.VERIFIED, method="mission_postconditions",
                reason="all required postconditions independently observed", evidence=evidence,
                verifier="uni.operator.executor")
            outcome = TaskOutcome.finalize(command=goal, message="Mission independently verified",
                actions=actions, observations=observations, verification=decision,
                failure_status=TaskStatus.VERIFIED)
            self._event(mission_id, ProgressState.VERIFIED)
            return outcome
        except InputStopped:
            return finish("STOP_REQUESTED", TaskStatus.INTERRUPTED)
        except asyncio.CancelledError:
            self._event(mission_id, ProgressState.STOPPED)
            raise
        except Exception as exc:
            # Terminal boundary preserves truth even for a broken provider/planner.
            return finish(f"{type(exc).__name__}: {exc}")
