from __future__ import annotations

from dataclasses import dataclass, field

from uni.devcoord.dispatcher import PreparedDispatch, TaskDispatcher
from uni.devcoord.mawc_sessions import AgentSessionManager
from uni.devcoord.reporter import DevelopmentReport, DevelopmentReporter
from uni.devcoord.runner import AgentRun, LocalAgentRunner
from uni.devcoord.workspace_models import SessionState, WorkspaceEvent
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
    ) -> None:
        self.store = store
        self.dispatcher = dispatcher
        self.runner = runner
        self.reporter = DevelopmentReporter(store)
        self.sessions = AgentSessionManager(store)
        self.profiles = {profile.agent_id: profile for profile in profiles}
        self._active_runs: dict[str, AgentRun] = {}

    def tick(self, *, ttl_seconds: float = 600.0) -> SupervisorTick:
        result = SupervisorTick()
        self._poll_runs(result, ttl_seconds=ttl_seconds)
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
                prepared = self.dispatcher.prepare(
                    session.session_id,
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
