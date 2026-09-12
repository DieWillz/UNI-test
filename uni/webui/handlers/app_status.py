"""Runtime status endpoint for the canonical UNI WebUI."""
from __future__ import annotations

from . import registry


def _workspace_snapshot(root, *, include_entities: bool = True) -> dict:
    db_path = root / ".uni-dev" / "coordination" / "workspace.sqlite"
    if not db_path.is_file():
        return {"available": False}
    try:
        from uni.devcoord.leases import ResourceLeaseManager
        from uni.devcoord.reporter import DevelopmentReporter
        from uni.devcoord.workspace_status import WorkspaceStatus
        from uni.devcoord.workspace_store import WorkspaceStore

        store = WorkspaceStore(db_path, initialize=False, read_only=True)
        summary = WorkspaceStatus(store).summary().model_dump(mode="json")
        report = DevelopmentReporter(store).snapshot().model_dump(mode="json")
        snapshot = {
            "available": True,
            "summary": summary,
            "session_counts": report["session_counts"],
            "task_counts": report["task_counts"],
            "lease_counts": report["lease_counts"],
            "critical_events": report["critical_events"],
        }
        if include_entities:
            snapshot.update({
                "tasks": [item.model_dump(mode="json") for item in store.list_workspace_tasks()],
                "sessions": [item.model_dump(mode="json") for item in store.list_sessions()],
                "leases": [item.model_dump(mode="json") for item in ResourceLeaseManager(store).list_active()],
                "events": [item.model_dump(mode="json") for item in store.list_events(limit=100)],
            })
        return snapshot
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _motion_running(motion) -> bool:
    if motion is None:
        return False
    try:
        return bool(getattr(motion, "status", lambda: {})().get("running"))
    except Exception:
        return False


def _intiface_snapshot(intiface) -> dict:
    if intiface is None:
        return {"connected": False, "devices": [], "url": "ws://127.0.0.1:12345"}
    try:
        snapshot = intiface.status()
        if not isinstance(snapshot, dict):
            raise TypeError("intiface status must be a mapping")
        return snapshot
    except Exception:
        return {"connected": False, "devices": [], "status": "unavailable"}


def _remote_snapshot(remote) -> dict:
    if remote is None:
        return {"active": False, "connected": False}
    try:
        return {
            "active": not remote.is_expired(),
            "connected": bool(remote.connected),
        }
    except Exception:
        return {"active": False, "connected": False, "status": "unavailable"}


def _app_status(handler) -> None:
    # Import lazily: handlers are registered while uni.webui.server is still
    # importing, so reading server globals at module import time is circular.
    import uni.webui.server as srv

    config_ok = True
    try:
        cfg = srv.load_config()
        autonomous_config = {
            "enabled": bool(cfg.autonomous.enabled),
            "auto_start_session": bool(cfg.autonomous.auto_start_session),
        }
    except Exception:
        config_ok = False
        autonomous_config = {
            "enabled": False,
            "auto_start_session": False,
            "status": "unavailable",
        }

    agent = srv._CHAT_AGENT
    autonomous = getattr(agent, "autonomous", None) if agent is not None else None
    autonomous_tasks = getattr(autonomous, "_tasks", set()) if autonomous is not None else set()
    session_state = getattr(agent, "state", None) if agent is not None else None
    voice_active = bool(session_state and getattr(session_state, "voice_listening", False))

    session = getattr(srv, "_XT_SESSION", None)
    motion = getattr(srv, "_MOTION", None)
    pattern = getattr(srv, "_XTOYS_PATTERN", None)
    intiface = getattr(srv, "_INTIFACE", None)
    coordinator = getattr(srv, "_TOY_COORDINATOR", None)
    remote = getattr(coordinator, "remote_session", None) if coordinator is not None else None

    intiface_snapshot = _intiface_snapshot(intiface)
    remote_snapshot = _remote_snapshot(remote)
    workspace_snapshot = _workspace_snapshot(srv._ROOT, include_entities=False)
    runtime_degraded = (
        any(
            snapshot.get("status") == "unavailable"
            for snapshot in (intiface_snapshot, remote_snapshot)
        )
        or bool(workspace_snapshot.get("error"))
    )

    handler._json(200, {
        "app": {
            "version": "3.3",
            "port": int(getattr(getattr(handler, "server", None), "server_port", 8787)),
            "server": "UNI WebUI",
            "control_mode": getattr(srv, "_CONTROL_MODE", "auto"),
            "autonomous": {
                **autonomous_config,
                "running": bool(autonomous_tasks),
            },
            "dorch": {
                "live_session": bool(session and getattr(session, "active", False)),
                "pattern_running": bool(pattern and getattr(pattern, "running", False)),
                "motion_running": _motion_running(motion),
                "emergency_stop": bool(getattr(coordinator, "emergency_stopped", False)),
            },
            "intiface": intiface_snapshot,
            "remote": remote_snapshot,
            "voice": {"listening": voice_active},
            "chat": {"agent_ready": agent is not None},
            "workspace": workspace_snapshot,
        },
        "status": "degraded" if (not config_ok or runtime_degraded) else "ok",
    })


registry.register("GET", "/api/app", _app_status, "UNI runtime app status")


def _workspace_admin(handler) -> None:
    if handler.client_address[0] not in ("127.0.0.1", "::1"):
        handler._json(403, {"error": "admin workspace is localhost-only"})
        return

    import uni.webui.server as srv

    handler._json(200, _workspace_snapshot(srv._ROOT))


registry.register(
    "GET",
    "/api/admin/workspace",
    _workspace_admin,
    "MAWC workspace runtime status",
)
