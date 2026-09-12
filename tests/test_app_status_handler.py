from types import SimpleNamespace

from uni.webui.handlers import app_status


class _Handler:
    def __init__(self, port: int) -> None:
        self.server = SimpleNamespace(server_port=port)
        self.status = None
        self.payload = None

    def _json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def test_app_status_reports_actual_bound_port(monkeypatch):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=True, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    handler = _Handler(8791)
    app_status._app_status(handler)
    assert handler.status == 200
    assert handler.payload["app"]["port"] == 8791


def test_app_status_marks_runtime_degraded_when_intiface_probe_fails(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    class BrokenIntiface:
        def status(self):
            raise RuntimeError("probe failed")

    monkeypatch.setattr(srv, "_INTIFACE", BrokenIntiface())
    handler = _Handler(8787)
    app_status._app_status(handler)

    assert handler.payload["status"] == "degraded"


def test_app_status_keeps_working_when_intiface_status_probe_fails(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    class BrokenIntiface:
        def status(self):
            raise RuntimeError("probe failed")

    monkeypatch.setattr(srv, "_INTIFACE", BrokenIntiface())
    handler = _Handler(8787)
    app_status._app_status(handler)

    assert handler.status == 200
    assert handler.payload["app"]["intiface"] == {
        "connected": False, "devices": [], "status": "unavailable"
    }
    assert handler.payload["app"]["workspace"] == {"available": False}


def test_app_status_keeps_working_when_motion_status_probe_fails(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    class BrokenMotion:
        def status(self):
            raise RuntimeError("motion probe failed")

    monkeypatch.setattr(srv, "_MOTION", BrokenMotion())
    handler = _Handler(8787)
    app_status._app_status(handler)

    assert handler.status == 200
    assert handler.payload["app"]["dorch"]["motion_running"] is False
    assert handler.payload["app"]["workspace"] == {"available": False}


def test_app_status_reports_workspace_summary_without_creating_missing_db(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    db_path = tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite"
    handler = _Handler(8787)
    app_status._app_status(handler)

    assert handler.payload["app"]["workspace"] == {"available": False}
    assert not db_path.exists()


def test_workspace_snapshot_does_not_initialize_existing_empty_db(tmp_path):
    db_path = tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    snapshot = app_status._workspace_snapshot(tmp_path, include_entities=False)

    assert snapshot["available"] is False
    assert db_path.stat().st_size == 0


def test_app_status_reports_workspace_counts(monkeypatch, tmp_path):
    import uni.webui.server as srv
    from uni.devcoord.workspace_models import AgentSession, WorkspaceTask, WorkTaskState
    from uni.devcoord.workspace_store import WorkspaceStore

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    store = WorkspaceStore(tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite")
    store.save_session(AgentSession(agent_id="chatgpt", display_name="ChatGPT"))
    store.save_workspace_task(WorkspaceTask(title="Admin UI", state=WorkTaskState.READY))

    handler = _Handler(8787)
    app_status._app_status(handler)
    workspace = handler.payload["app"]["workspace"]
    assert workspace["available"] is True
    assert workspace["summary"]["active_sessions"] == 1
    assert workspace["task_counts"] == {"ready": 1}


def test_app_status_keeps_working_when_remote_expiry_probe_fails(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE"):
        monkeypatch.setattr(srv, name, None)

    class BrokenRemote:
        connected = True
        def is_expired(self):
            raise RuntimeError("remote probe failed")

    coordinator = SimpleNamespace(remote_session=BrokenRemote(), emergency_stopped=False)
    monkeypatch.setattr(srv, "_TOY_COORDINATOR", coordinator)
    handler = _Handler(8787)

    app_status._app_status(handler)

    assert handler.status == 200
    assert handler.payload["app"]["remote"] == {
        "active": False, "connected": False, "status": "unavailable"
    }


def test_app_status_keeps_working_when_config_load_fails(monkeypatch, tmp_path):
    import uni.webui.server as srv

    def broken_config():
        raise ValueError("invalid config")

    monkeypatch.setattr(srv, "load_config", broken_config)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    handler = _Handler(8787)
    app_status._app_status(handler)

    assert handler.status == 200
    assert handler.payload["app"]["autonomous"] == {
        "enabled": False,
        "auto_start_session": False,
        "running": False,
        "status": "unavailable",
    }
    assert handler.payload["status"] == "degraded"


def test_app_status_marks_degraded_when_existing_workspace_db_is_unreadable(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_INTIFACE", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    db_path = tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("not a sqlite database", encoding="utf-8")

    handler = _Handler(8787)
    app_status._app_status(handler)

    workspace = handler.payload["app"]["workspace"]
    assert workspace["available"] is False
    assert "error" in workspace
    assert handler.payload["status"] == "degraded"


def test_app_status_keeps_working_when_intiface_returns_malformed_status(monkeypatch, tmp_path):
    import uni.webui.server as srv

    cfg = SimpleNamespace(autonomous=SimpleNamespace(enabled=False, auto_start_session=False))
    monkeypatch.setattr(srv, "load_config", lambda: cfg)
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    for name in ("_CHAT_AGENT", "_XT_SESSION", "_MOTION", "_XTOYS_PATTERN", "_TOY_COORDINATOR"):
        monkeypatch.setattr(srv, name, None)

    class MalformedIntiface:
        def status(self):
            return None

    monkeypatch.setattr(srv, "_INTIFACE", MalformedIntiface())
    handler = _Handler(8787)

    app_status._app_status(handler)

    assert handler.status == 200
    assert handler.payload["status"] == "degraded"
    assert handler.payload["app"]["intiface"] == {
        "connected": False, "devices": [], "status": "unavailable"
    }

def test_workspace_snapshot_opens_store_read_only(monkeypatch, tmp_path):
    from uni.devcoord import workspace_store as workspace_store_module
    from uni.devcoord.workspace_store import WorkspaceStore as RealWorkspaceStore

    db_path = tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite"
    RealWorkspaceStore(db_path)
    seen = {}

    class SpyWorkspaceStore(RealWorkspaceStore):
        def __init__(self, path, *, initialize=True, read_only=False):
            seen["initialize"] = initialize
            seen["read_only"] = read_only
            super().__init__(path, initialize=initialize, read_only=read_only)

    monkeypatch.setattr(workspace_store_module, "WorkspaceStore", SpyWorkspaceStore)
    snapshot = app_status._workspace_snapshot(tmp_path, include_entities=False)

    assert snapshot["available"] is True
    assert seen == {"initialize": False, "read_only": True}

