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


def test_read_claim_does_not_block_non_overlapping_write(tmp_path: Path) -> None:
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
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/agent.py", access_mode=AccessMode.WRITE)],
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


def test_read_read_allowed(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "reader-a", "READ-A")
    _register(store, "reader-b", "READ-B")
    manager = ResourceLeaseManager(store)
    request = ResourceRequest(
        resource_type=ResourceType.FILE,
        resource_key="uni/brain.py",
        access_mode=AccessMode.READ,
    )
    manager.claim("READ-A", "reader-a", [request])
    manager.claim("READ-B", "reader-b", [request])
    assert len(manager.list_active()) == 2


def test_read_then_write_conflicts(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "reader", "READ")
    _register(store, "writer", "WRITE")
    manager = ResourceLeaseManager(store)
    manager.claim(
        "READ",
        "reader",
        [ResourceRequest(
            resource_type=ResourceType.FILE,
            resource_key="uni/brain.py",
            access_mode=AccessMode.READ,
        )],
    )
    with pytest.raises(LeaseConflictError):
        manager.claim(
            "WRITE",
            "writer",
            [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
        )


def test_write_then_read_conflicts(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "writer", "WRITE")
    _register(store, "reader", "READ")
    manager = ResourceLeaseManager(store)
    manager.claim(
        "WRITE", "writer",
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")],
    )
    with pytest.raises(LeaseConflictError):
        manager.claim(
            "READ", "reader",
            [ResourceRequest(
                resource_type=ResourceType.FILE,
                resource_key="uni/brain.py",
                access_mode=AccessMode.READ,
            )],
        )


def test_exclusive_blocks_any_other_access(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    for session_id in ("owner", "reader", "writer"):
        _register(store, session_id, session_id)
    manager = ResourceLeaseManager(store)
    manager.claim(
        "owner", "owner",
        [ResourceRequest(
            resource_type=ResourceType.LOGIC,
            resource_key="autonomous-loop",
            access_mode=AccessMode.EXCLUSIVE,
        )],
    )
    for session_id, mode in (("reader", AccessMode.READ), ("writer", AccessMode.WRITE)):
        with pytest.raises(LeaseConflictError):
            manager.claim(
                session_id,
                session_id,
                [ResourceRequest(
                    resource_type=ResourceType.LOGIC,
                    resource_key="autonomous-loop",
                    access_mode=mode,
                )],
            )


def test_duplicate_requests_collapse_to_one_strongest_lease(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "owner", "OWNER")
    manager = ResourceLeaseManager(store)
    leases = manager.claim(
        "OWNER",
        "owner",
        [
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="UNI\\brain.py", access_mode=AccessMode.READ),
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py", access_mode=AccessMode.WRITE),
            ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py", access_mode=AccessMode.READ),
        ],
    )

    assert len(leases) == 1
    assert leases[0].resource_key == "uni/brain.py"
    assert leases[0].access_mode is AccessMode.WRITE
    assert len(manager.list_active()) == 1


def test_exact_same_owner_claim_is_idempotent(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "owner", "OWNER")
    manager = ResourceLeaseManager(store)
    request = ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/brain.py")

    first = manager.claim("OWNER", "owner", [request])
    second = manager.claim("OWNER", "owner", [request])

    assert [lease.lease_id for lease in second] == [lease.lease_id for lease in first]
    assert len(manager.list_active()) == 1


def test_same_owner_can_upgrade_read_to_write_without_duplicate(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "owner", "OWNER")
    manager = ResourceLeaseManager(store)
    read = ResourceRequest(
        resource_type=ResourceType.FILE,
        resource_key="uni/brain.py",
        access_mode=AccessMode.READ,
    )
    write = read.model_copy(update={"access_mode": AccessMode.WRITE})

    first = manager.claim("OWNER", "owner", [read])
    upgraded = manager.claim("OWNER", "owner", [write])

    assert upgraded[0].lease_id == first[0].lease_id
    assert upgraded[0].access_mode is AccessMode.WRITE
    active = manager.list_active()
    assert len(active) == 1
    assert active[0].access_mode is AccessMode.WRITE


def test_same_owner_upgrade_still_respects_other_reader(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    _register(store, "owner", "OWNER")
    _register(store, "other", "OTHER")
    manager = ResourceLeaseManager(store)
    read = ResourceRequest(
        resource_type=ResourceType.FILE,
        resource_key="uni/brain.py",
        access_mode=AccessMode.READ,
    )
    manager.claim("OWNER", "owner", [read])
    manager.claim("OTHER", "other", [read])

    with pytest.raises(LeaseConflictError):
        manager.claim(
            "OWNER",
            "owner",
            [read.model_copy(update={"access_mode": AccessMode.WRITE})],
        )

    active = manager.list_active()
    assert len(active) == 2
    assert all(lease.access_mode is AccessMode.READ for lease in active)
