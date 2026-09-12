"""Unified Development / Workspace API adapters for the admin UI."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import registry


def _is_local(handler) -> bool:
    return handler.client_address[0] in ("127.0.0.1", "::1")


def _master_revision(root: Path) -> str:
    try:
        from uni.direction_sync import DirectionSyncGate
        gate = DirectionSyncGate(
            root / "docs" / "handoffs" / "UNI_MASTER_DIRECTION.md",
            root / "docs" / "handoffs" / "UNI_ACTIVE_WORK.md",
            root / ".uni-dev" / "coordination" / "direction_ack.json",
        )
        revision, _assignments = gate._snapshot()
        return revision
    except Exception:
        return ""


def _task_status(task) -> str:
    if bool(getattr(task, "owner_verified", False)):
        return "OWNER VERIFIED"
    state = str(getattr(task, "state", "planned"))
    if "." in state:
        state = state.rsplit(".", 1)[-1]
    key = state.lower()
    if key in {"planned", "ready"}:
        return "PLANNED"
    if key in {"claimed", "active"}:
        return "ACTIVE"
    if key == "verifying":
        return "VERIFYING"
    if key in {"verified", "merged"}:
        return "WAITING OWNER"
    if key in {"blocked", "conflict"}:
        return "BLOCKED"
    if key == "stale":
        return "STALE"
    if key in {"failed", "abandoned"}:
        return "FAILED"
    return key.upper()


def _task_progress(task) -> tuple[int, int, int, bool]:
    from uni.workspace import calculate_progress

    items = list(getattr(task, "acceptance_items", ()) or ())
    total = len(items)
    passed = sum(1 for item in items if bool(getattr(item, "passed", False)))
    state = str(getattr(task, "state", ""))
    if "." in state:
        state = state.rsplit(".", 1)[-1]
    agent_verified = state.lower() in {"verified", "merged"}
    owner_verified = bool(getattr(task, "owner_verified", False))
    progress = calculate_progress(total, passed, agent_verified, owner_verified)
    return progress, passed, total, agent_verified


def _checkpoint_views(root: Path) -> list[dict[str, Any]]:
    try:
        from uni.checkpoints import CheckpointManager, CheckpointType
        manager = CheckpointManager(root)
        checkpoints = list(manager.list_checkpoints())
        try:
            head = manager.git.head_revision()
            clean = manager.git.is_clean()
        except Exception:
            head, clean = "", False
        return [
            {
                "id": item.id,
                "label": item.label,
                "created_at": item.created_at,
                "type": item.type.value,
                "reference": item.snapshot_ref,
                "master_revision": item.master_revision,
                "source_git_revision": item.source_git_revision,
                "snapshot_ref": item.snapshot_ref,
                "owner_verified": bool(item.owner_verified_at),
                "owner_verified_at": item.owner_verified_at,
                "current": bool(clean and item.type is CheckpointType.PROJECT_KNOWN_GOOD and item.source_git_revision == head),
                "features": list(item.verified_features),
                "verified_features": list(item.verified_features),
                "test_evidence": list(item.test_evidence),
            }
            for item in checkpoints
        ]
    except Exception:
        return []


def _workspace_overview(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    revision = _master_revision(root)
    now = datetime.now(timezone.utc).isoformat()
    db_path = root / ".uni-dev" / "coordination" / "workspace.sqlite"
    checkpoints = _checkpoint_views(root)
    if not db_path.is_file():
        return {
            "master_revision": revision,
            "updated_at": now,
            "agents": [],
            "tasks": [],
            "checkpoints": checkpoints,
        }

    from uni.devcoord.leases import ResourceLeaseManager
    from uni.devcoord.workspace_store import WorkspaceStore

    store = WorkspaceStore(db_path, initialize=False, read_only=True)
    sessions = store.list_sessions()
    tasks = store.list_workspace_tasks()
    leases = ResourceLeaseManager(store).list_active()
    by_task = {task.id: task for task in tasks}
    by_session = {session.session_id: session for session in sessions}
    timestamps: list[str] = [now]
    agents: list[dict[str, Any]] = []
    for session in sessions:
        task = by_task.get(session.task_id or "")
        progress = _task_progress(task)[0] if task is not None else 0
        owned_paths = []
        for lease in leases:
            rtype = getattr(getattr(lease, "resource_type", None), "value", "")
            if lease.agent_session_id == session.session_id and rtype in {"file", "tree"}:
                owned_paths.append(lease.resource_key)
        state = getattr(getattr(session, "state", None), "value", str(getattr(session, "state", "")))
        stale = bool(getattr(session, "direction_stale", False) or str(state).lower() == "stale")
        status = "STALE" if stale else ("VERIFYING" if str(state).lower() == "verifying" else ("ACTIVE" if session.task_id else "PLANNED"))
        blockers = list(getattr(task, "blockers", ()) or ()) if task is not None else []
        agents.append({
            "id": session.session_id,
            "name": session.display_name,
            "task": session.task_id,
            "status": status,
            "progress": progress,
            "updated_at": session.heartbeat_at,
            "direction_revision": revision,
            "ack_revision": session.direction_revision_ack or "",
            "stale": stale,
            "owned_paths": sorted(set(owned_paths)),
            "blockers": blockers,
        })
        timestamps.append(session.heartbeat_at)

    task_views: list[dict[str, Any]] = []
    for task in tasks:
        progress, passed, total, agent_verified = _task_progress(task)
        session = by_session.get(task.assigned_session_id or "")
        task_views.append({
            "id": task.id,
            "title": task.title,
            "description": "",
            "agent": session.display_name if session else task.assigned_session_id,
            "status": _task_status(task),
            "progress": progress,
            "updated_at": task.updated_at,
            "acceptance_total": total,
            "acceptance_passed": passed,
            "agent_verified": agent_verified,
            "owner_verified": bool(task.owner_verified),
            "owner_verified_at": None,
            "owner_note": "",
            "dependencies": list(task.dependencies),
            "owner_verified_by": None,
            "task_revision": "",
            "verification_evidence_ref": "",
            "source_revision": revision,
            "owner_verification": None,
        })
        timestamps.append(task.updated_at)
    timestamps.extend(item.get("created_at", "") for item in checkpoints)
    return {
        "master_revision": revision,
        "updated_at": max((item for item in timestamps if item), default=now),
        "agents": agents,
        "tasks": task_views,
        "checkpoints": checkpoints,
    }


def _overview(handler) -> None:
    if not _is_local(handler):
        handler._json(403, {"error": "workspace overview is localhost-only"})
        return
    import uni.webui.server as srv
    handler._json(200, _workspace_overview(srv._ROOT))


def _path_parts(handler) -> list[str]:
    path = str(handler.path).split("?", 1)[0]
    return [part for part in path.split("/") if part]


def _owner_verification(handler) -> None:
    if not _is_local(handler):
        handler._json(403, {"error": "owner verification is localhost-only"})
        return
    parts = _path_parts(handler)
    if len(parts) != 5 or parts[:3] != ["api", "workspace", "tasks"] or parts[4] != "owner-verification":
        handler._json(404, {"error": "unknown workspace owner-verification route"})
        return
    body = handler._read_json_body() or {}
    if not isinstance(body.get("verified"), bool) or not str(body.get("note", "")).strip():
        handler._json(400, {"error": "verified boolean and non-empty note are required"})
        return
    import uni.webui.server as srv
    from uni.devcoord.workspace_store import WorkspaceStore
    db_path = Path(srv._ROOT) / ".uni-dev" / "coordination" / "workspace.sqlite"
    if not db_path.is_file():
        handler._json(404, {"error": "workspace task store is unavailable"})
        return
    store = WorkspaceStore(db_path, initialize=False, read_only=True)
    try:
        task = store.get_workspace_task(parts[3])
    except KeyError:
        handler._json(404, {"error": f"unknown workspace task: {parts[3]}"})
        return
    missing = []
    for field in ("task_revision", "verification_evidence_ref", "owner_verification"):
        if not hasattr(task, field):
            missing.append(field)
    if missing:
        handler._json(409, {
            "error": "Owner verification evidence cannot be persisted by the current MAWC task schema; "
                     "missing evidence/revision fields: " + ", ".join(missing),
            "owner_verified": bool(task.owner_verified),
        })
        return
    handler._json(409, {"error": "Owner verification persistence adapter is not available yet."})


def _restore_plan(handler) -> None:
    if not _is_local(handler):
        handler._json(403, {"error": "restore planning is localhost-only"})
        return
    parts = _path_parts(handler)
    if len(parts) != 5 or parts[:3] != ["api", "workspace", "checkpoints"] or parts[4] != "restore-plan":
        handler._json(404, {"error": "unknown workspace restore-plan route"})
        return
    import uni.webui.server as srv
    from uni.checkpoints import CheckpointError, CheckpointManager, UnknownCheckpointError
    manager = CheckpointManager(Path(srv._ROOT))
    try:
        plan = manager.prepare_restore(parts[3])
    except UnknownCheckpointError as exc:
        handler._json(404, {"error": f"unknown checkpoint: {exc}"})
        return
    except CheckpointError as exc:
        handler._json(409, {"error": str(exc)})
        return
    handler._json(200, {
        "source_checkpoint": plan.source_checkpoint.to_dict(),
        "target_revision": plan.target_revision,
        "changed_files": list(plan.changed_files),
        "files_that_would_be_removed": list(plan.files_that_would_be_removed),
        "conflicts": list(plan.conflicts),
        "current_dirty_state": list(plan.current_dirty_state),
        "safe_target_workspace": plan.safe_target_workspace,
        "activation_allowed": bool(plan.activation_allowed),
    })


registry.register("GET", "/api/workspace/overview", _overview, "Unified workspace overview")
registry.register("POST", "/api/workspace/tasks/*", _owner_verification, "Owner task verification")
registry.register("POST", "/api/workspace/checkpoints/*", _restore_plan, "Prepare checkpoint restore plan")
