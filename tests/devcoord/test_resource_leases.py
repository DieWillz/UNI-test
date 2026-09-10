from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uni.devcoord.lease_rules import resources_overlap
from uni.devcoord.leases import LeaseConflictError, ResourceLeaseManager
from uni.devcoord.workspace_models import (
    AccessMode,
    AgentSession,
    LeaseState,
    ResourceRequest,
    ResourceType,
)
from uni.devcoord.workspace_store import WorkspaceStore


def _register(store: WorkspaceStore, session_id: str, task_id: str) -> None:
    store.save_session(
        AgentSession(
            session_id=session_id,
            agent_id=session_id,
            display_name=session_id,
            task_id=task_id,
        )
    )


def test_resource_overlap_rules_cover_file_tree_and_logic() -> None:
    assert resources_overlap(ResourceType.FILE, "uni/Brain.py", ResourceType.FILE, "UNI\\brain.py")
    assert resources_overlap(ResourceType.TREE, "uni/transports", ResourceType.FILE, "uni/transports/telegram/adapter.py")
    assert resources_overlap(ResourceType.FILE, "uni/transports/telegram/adapter.py", ResourceType.TREE, "UNI\\TRANSPORTS")
    assert resources_overlap(ResourceType.LOGIC, "autonomous-loop", ResourceType.LOGIC, "AUTONOMOUS-LOOP")
    assert not resources_overlap(ResourceType.FILE, "uni/brain.py", ResourceType.FILE, "uni/agent.py")
    assert not resources_overlap(ResourceType.TREE, "uni/operator", ResourceType.FILE, "uni/transports/a.py")
    assert not resources_overlap(ResourceType.LOGIC, "voice", ResourceType.LOGIC, "browser")


def test_conflicting_write_claim_is_denied(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "hermes", "UNI-1")
    _register(store, "codex", "UNI-2")
    manager = ResourceLeaseManager(store)

    first = manager.claim(
        "UNI-1",
        "hermes",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )

    with pytest.raises(LeaseConflictError) as exc:
        manager.claim(
            "UNI-2",
            "codex",
            [ResourceRequest(resource_type=ResourceType.FILE, resource_key="UNI\\brain.py")],
            ttl_seconds=600,
        )

    assert len(first) == 1
    assert exc.value.conflicts[0].agent_session_id == "hermes"
    assert len(manager.list_active()) == 1


def test_multi_resource_claim_is_all_or_nothing(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "hermes", "UNI-1")
    _register(store, "codex", "UNI-2")
    manager = ResourceLeaseManager(store)
    manager.claim(
        "UNI-1",
        "hermes",
        [ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="voice-runtime")],
        ttl_seconds=600,
    )

    with pytest.raises(LeaseConflictError):
        manager.claim(
            "UNI-2",
            "codex",
            [
                ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/free.py"),
                ResourceRequest(resource_type=ResourceType.LOGIC, resource_key="voice-runtime"),
            ],
            ttl_seconds=600,
        )

    active_keys = {lease.resource_key for lease in manager.list_active()}
    assert active_keys == {"voice-runtime"}


def test_read_claim_does_not_block_write_in_v1(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "reader", "UNI-1")
    _register(store, "writer", "UNI-2")
    manager = ResourceLeaseManager(store)
    manager.claim(
        "UNI-1",
        "reader",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py", access_mode=AccessMode.READ)],
        ttl_seconds=600,
    )
    manager.claim(
        "UNI-2",
        "writer",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py", access_mode=AccessMode.WRITE)],
        ttl_seconds=600,
    )

    assert len(manager.list_active()) == 2


def test_release_records_final_hash_and_unlocks_resource(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "hermes", "UNI-1")
    _register(store, "codex", "UNI-2")
    manager = ResourceLeaseManager(store)
    lease = manager.claim(
        "UNI-1",
        "hermes",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )[0]

    released = manager.release(lease.lease_id, current_hash="a" * 64)
    assert released.state is LeaseState.RELEASED
    assert released.current_hash == "a" * 64
    second = manager.claim(
        "UNI-2",
        "codex",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        ttl_seconds=600,
    )
    assert len(second) == 1



def test_two_processes_cannot_both_claim_same_write_resource(tmp_path: Path) -> None:
    db_path = tmp_path / "workspace.sqlite"
    store = WorkspaceStore(db_path)
    _register(store, "agent-a", "task-agent-a")
    _register(store, "agent-b", "task-agent-b")
    start_path = tmp_path / "start"
    code = """
import sys, time
from pathlib import Path
from uni.devcoord.leases import LeaseConflictError, ResourceLeaseManager
from uni.devcoord.workspace_models import ResourceRequest, ResourceType
from uni.devcoord.workspace_store import WorkspaceStore

db_path, session_id, start_path, result_path = sys.argv[1:]
while not Path(start_path).exists():
    time.sleep(0.01)
try:
    ResourceLeaseManager(WorkspaceStore(db_path)).claim(
        f"task-{session_id}", session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/race.py")],
        ttl_seconds=600,
    )
except LeaseConflictError:
    result = "conflict"
else:
    result = "ok"
Path(result_path).write_text(result, encoding="utf-8")
"""
    result_paths = [tmp_path / "a.txt", tmp_path / "b.txt"]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(db_path), session_id, str(start_path), str(result_path)],
            cwd=str(Path(__file__).parents[2]),
        )
        for session_id, result_path in zip(("agent-a", "agent-b"), result_paths)
    ]
    start_path.write_text("go", encoding="utf-8")
    for process in processes:
        assert process.wait(timeout=15) == 0

    results = sorted(path.read_text(encoding="utf-8") for path in result_paths)
    assert results == ["conflict", "ok"]
    assert len(ResourceLeaseManager(WorkspaceStore(db_path)).list_active()) == 1
