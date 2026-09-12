from __future__ import annotations

import subprocess
from pathlib import Path

from uni.devcoord.leases import ResourceLeaseManager
from uni.devcoord.workspace_models import (
    AccessMode,
    AgentSession,
    LeaseState,
    ResourceRequest,
    ResourceType,
)
from uni.devcoord.workspace_monitor import GuardDecision, WorkspaceMonitor
from uni.devcoord.workspace_store import WorkspaceStore


def _session(store: WorkspaceStore, session_id: str, agent_id: str, task_id: str) -> None:
    store.save_session(AgentSession(
        session_id=session_id,
        agent_id=agent_id,
        display_name=agent_id.title(),
        task_id=task_id,
    ))


def _claim_file(store: WorkspaceStore, task_id: str, session_id: str, path: str, mode=AccessMode.WRITE):
    return ResourceLeaseManager(store).claim(
        task_id,
        session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key=path, access_mode=mode)],
    )[0]


def test_can_write_allows_owned_write_lease(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")

    result = WorkspaceMonitor(store).can_write("hermes", "uni/brain.py")

    assert result.decision is GuardDecision.ALLOW
    assert result.lease_id == lease.lease_id
    assert result.task_id == "TASK-A"
    assert result.resource == "file:uni/brain.py"


def test_can_write_denies_when_another_agent_owns_resource(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")

    result = WorkspaceMonitor(store).can_write("codex", "UNI\\brain.py")

    assert result.decision is GuardDecision.DENY
    assert result.owner == "hermes"
    assert result.agent == "codex"
    assert result.task_id == "TASK-A"
    assert result.lease_id == lease.lease_id
    assert result.expires_at == lease.expires_at


def test_can_write_warns_when_no_write_lease_exists(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-codex", "codex", "TASK-C")
    result = WorkspaceMonitor(store).can_write("codex", "uni/free.py")
    assert result.decision is GuardDecision.ALLOW_WITH_WARNING
    assert result.agent == "codex"
    assert result.owner is None
    assert "no active write lease" in result.reason.lower()


def test_audit_paths_emits_event_for_unleased_path(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")
    monitor = WorkspaceMonitor(store)
    findings = monitor.audit_paths(["uni/brain.py", "uni/agent.py"])
    assert [item.path for item in findings] == ["uni/agent.py"]
    assert findings[0].event == "workspace.unowned_change"
    events = store.list_events(limit=20)
    assert any(event.resource_key == "uni/agent.py" for event in events)


def test_audit_paths_reports_violation_for_other_session(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    _session(store, "s-codex", "codex", "TASK-C")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")
    findings = WorkspaceMonitor(store).audit_paths(
        ["uni/brain.py"], expected_session_id="s-codex"
    )
    assert len(findings) == 1
    assert findings[0].event == "workspace.ownership_violation"
    assert findings[0].lease_id == lease.lease_id
    assert findings[0].session_id == "s-codex"


def test_git_changed_paths_returns_modified_and_untracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    tracked.write_text("after\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    changed = WorkspaceMonitor(store).git_changed_paths(repo)
    assert changed == ["new.txt", "tracked.txt"]


def test_can_write_denies_own_stale_lease(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")
    store.save_resource_lease(lease.model_copy(update={"state": LeaseState.STALE}))

    result = WorkspaceMonitor(store).can_write("hermes", "uni/brain.py")

    assert result.decision is GuardDecision.DENY
    assert result.lease_id == lease.lease_id
    assert "stale" in result.reason.lower() or "expired" in result.reason.lower()


def test_can_write_denies_own_expired_active_lease(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")
    store.save_resource_lease(lease.model_copy(update={
        "expires_at": "2000-01-01T00:00:00+00:00"
    }))

    result = WorkspaceMonitor(store).can_write("hermes", "uni/brain.py")

    assert result.decision is GuardDecision.DENY
    assert result.lease_id == lease.lease_id
    assert "expired" in result.reason.lower()


def test_audit_expired_lease_does_not_authorize_write(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _session(store, "s-hermes", "hermes", "TASK-A")
    lease = _claim_file(store, "TASK-A", "s-hermes", "uni/brain.py")
    store.save_resource_lease(lease.model_copy(update={
        "expires_at": "2000-01-01T00:00:00+00:00"
    }))

    findings = WorkspaceMonitor(store).audit_paths(
        ["uni/brain.py"], expected_session_id="s-hermes"
    )

    assert len(findings) == 1
    assert findings[0].event in {"workspace.ownership_violation", "workspace.unowned_change"}
