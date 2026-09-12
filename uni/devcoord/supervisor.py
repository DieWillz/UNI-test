from __future__ import annotations

from dataclasses import dataclass, field

from uni.devcoord.dispatcher import PreparedDispatch, TaskDispatcher
from uni.devcoord.integration import IntegrationManager
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.reporter import DevelopmentReport, DevelopmentReporter
from uni.devcoord.runner import AgentRun, LocalAgentRunner
from uni.devcoord.verification import VerificationManager
from uni.devcoord.workspace_models import SessionState, WorkTaskState, WorkspaceEvent
from uni.devcoord.workspace_store import WorkspaceStore


@dataclass(frozen=True)
class AgentLaunchProfile:
    agent_id: str
    argv: list[str]

    def build_argv(self, prepared: PreparedDispatch) -> list[str]:
        if not self.argv or not self.argv[0].strip():
            raise ValueError("launch profile argv must contain an executable")
        replacements = {
            "{task_id}": prepared.task.id,
            "{session_id}": prepared.session.session_id,
            "{worktree}": str(prepared.worktree.path),
        }
        built: list[str] = []
        for token in self.argv:
            value = token
            for marker, replacement in replacements.items():
                value = value.replace(marker, replacement)
            built.append(value)
        return built


@dataclass(frozen=True)
class SupervisorFailure:
    session_id: str
    stage: str
    detail: str


@dataclass
class SupervisorTick:
    started_runs: list[AgentRun] = field(default_factory=list)
    finished_runs: list[AgentRun] = field(default_factory=list)
    verified_tasks: list[str] = field(default_factory=list)
    merged_tasks: list[str] = field(default_factory=list)
    failures: list[SupervisorFailure] = field(default_factory=list)
    report: DevelopmentReport | None = None


class DevelopmentSupervisor:
    """Run MAWC scheduling without declaring tasks verified."""

    def __init__(
        self,
        store: WorkspaceStore,
        dispatcher: TaskDispatcher,
        runner: LocalAgentRunner,
        *,
        profiles: list[AgentLaunchProfile],
        verification_manager: VerificationManager | None = None,
        integration_manager: IntegrationManager | None = None,
    ) -> None:
        self.store = store
        self.dispatcher = dispatcher
        self.runner = runner
        self.reporter = DevelopmentReporter(store)
        self.sessions = AgentSessionManager(store)
        self.verification_manager = verification_manager
        self.integration_manager = integration_manager
        self.profiles = {profile.agent_id: profile for profile in profiles}
        self._active_runs: dict[str, AgentRun] = {}

    def tick(self, *, ttl_seconds: float = 600.0) -> SupervisorTick:
        result = SupervisorTick()
        self._poll_runs(result, ttl_seconds=ttl_seconds)
        self._advance_lifecycle(result)
        self.sessions.mark_stale()
        self._dispatch_free_sessions(result, ttl_seconds=ttl_seconds)
        result.report = self.reporter.snapshot()
        return result

    def _poll_runs(self, result: SupervisorTick, *, ttl_seconds: float) -> None:
        for session_id, run in list(self._active_runs.items()):
            try:
                observation = self.runner.tick(run.run_id, ttl_seconds=ttl_seconds)
            except Exception as exc:
                self._record_failure(result, session_id, "poll", exc)
                continue
            if not observation.running:
                result.finished_runs.append(run)
                self._active_runs.pop(session_id, None)

    def _advance_lifecycle(self, result: SupervisorTick) -> None:
        for task in self.store.list_workspace_tasks():
            session_id = task.assigned_session_id
            if not session_id or session_id in self._active_runs:
                continue

            if task.state is WorkTaskState.VERIFYING and self.verification_manager is not None:
                try:
                    outcome = self.verification_manager.verify(task.id)
                except Exception as exc:
                    self._record_failure(result, session_id, "verification", exc)
                    continue
                if not outcome.passed:
                    continue
                result.verified_tasks.append(task.id)
                task = self.store.get_workspace_task(task.id)

            if task.state is WorkTaskState.VERIFIED and self.integration_manager is not None:
                try:
                    outcome = self.integration_manager.integrate(task.id)
                except Exception as exc:
                    self._record_failure(result, session_id, "integration", exc)
                    continue
                if outcome.merged:
                    result.merged_tasks.append(task.id)

    def _dispatch_free_sessions(
        self,
        result: SupervisorTick,
        *,
        ttl_seconds: float,
    ) -> None:
        for session in self.store.list_sessions():
            if session.state is not SessionState.ACTIVE:
                continue
            if session.task_id is not None or session.session_id in self._active_runs:
                continue
            profile = self.profiles.get(session.agent_id)
            if profile is None:
                continue
            try:
                base_ref = (
                    self.integration_manager.dispatch_base_ref()
                    if self.integration_manager is not None
                    else "HEAD"
                )
                prepared = self.dispatcher.prepare(
                    session.session_id,
                    base_ref=base_ref,
                    ttl_seconds=ttl_seconds,
                )
                if prepared is None:
                    self.sessions.heartbeat(session.session_id, ttl_seconds=ttl_seconds)
                    continue
                run = self.runner.start(prepared, profile.build_argv(prepared))
            except Exception as exc:
                self._record_failure(result, session.session_id, "dispatch", exc)
                continue
            self._active_runs[session.session_id] = run
            result.started_runs.append(run)

    def _record_failure(
        self,
        result: SupervisorTick,
        session_id: str,
        stage: str,
        error: Exception,
    ) -> None:
        detail = f"{type(error).__name__}: {error}"
        result.failures.append(
            SupervisorFailure(session_id=session_id, stage=stage, detail=detail)
        )
        current = self.store.get_session(session_id)
        self.store.append_event(
            WorkspaceEvent(
                event="supervisor.failure",
                task_id=current.task_id,
                session_id=session_id,
                detail=f"{stage}: {detail}"[:4000],
            )
        )
