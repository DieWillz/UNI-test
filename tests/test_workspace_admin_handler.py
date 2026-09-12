from uni.webui import handlers


def test_workspace_admin_route_is_registered():
    route = handlers.registry.match("GET", "/api/admin/workspace")
    assert route is not None


def test_workspace_snapshot_exposes_live_entities(tmp_path):
    from uni.devcoord.workspace_models import AgentSession, WorkspaceEvent, WorkspaceTask
    from uni.devcoord.workspace_store import WorkspaceStore
    from uni.webui.handlers.app_status import _workspace_snapshot

    root = tmp_path
    store = WorkspaceStore(root / ".uni-dev" / "coordination" / "workspace.sqlite")
    task = WorkspaceTask(id="task-1", title="Improve admin")
    session = AgentSession(agent_id="chatgpt", display_name="ChatGPT", task_id=task.id)
    store.save_workspace_task(task)
    store.save_session(session)
    store.append_event(WorkspaceEvent(event="task.created", task_id=task.id, detail="created"))

    snapshot = _workspace_snapshot(root)

    assert snapshot["tasks"][0]["id"] == "task-1"
    assert snapshot["sessions"][0]["agent_id"] == "chatgpt"
    assert snapshot["events"][0]["event"] == "task.created"


def test_workspace_snapshot_exposes_active_leases(tmp_path):
    from uni.devcoord.leases import ResourceLeaseManager
    from uni.devcoord.workspace_models import AgentSession, ResourceRequest, ResourceType
    from uni.devcoord.workspace_store import WorkspaceStore
    from uni.webui.handlers.app_status import _workspace_snapshot

    root = tmp_path
    store = WorkspaceStore(root / ".uni-dev" / "coordination" / "workspace.sqlite")
    session = AgentSession(agent_id="codex", display_name="Codex")
    store.save_session(session)
    ResourceLeaseManager(store).claim(
        "task-lease", session.session_id,
        [ResourceRequest(resource_type=ResourceType.FILE, resource_key="uni/webui/index.html")],
    )

    snapshot = _workspace_snapshot(root)

    assert snapshot["leases"][0]["resource_key"] == "uni/webui/index.html"


def test_workspace_snapshot_can_omit_heavy_entities(tmp_path):
    from uni.devcoord.workspace_models import WorkspaceTask
    from uni.devcoord.workspace_store import WorkspaceStore
    from uni.webui.handlers.app_status import _workspace_snapshot

    root = tmp_path
    store = WorkspaceStore(root / ".uni-dev" / "coordination" / "workspace.sqlite")
    store.save_workspace_task(WorkspaceTask(id="task-light", title="Light status"))

    snapshot = _workspace_snapshot(root, include_entities=False)

    assert snapshot["available"] is True
    assert snapshot["task_counts"]
    assert "tasks" not in snapshot
    assert "sessions" not in snapshot
    assert "leases" not in snapshot
    assert "events" not in snapshot


def test_workspace_admin_rejects_non_local_clients():
    from uni.webui.handlers.app_status import _workspace_admin

    class Handler:
        client_address = ("203.0.113.10", 50000)
        response = None

        def _json(self, status, payload):
            self.response = (status, payload)

    handler = Handler()
    _workspace_admin(handler)

    assert handler.response[0] == 403
    assert "localhost" in handler.response[1]["error"]


def test_unified_workspace_routes_are_registered():
    assert handlers.registry.match("GET", "/api/workspace/overview") is not None
    assert handlers.registry.match("POST", "/api/workspace/tasks/task-1/owner-verification") is not None
    assert handlers.registry.match("POST", "/api/workspace/checkpoints/cp-1/restore-plan") is not None


def test_workspace_overview_normalizes_mawc_entities(tmp_path):
    from uni.devcoord.workspace_models import AcceptanceItem, AgentSession, WorkTaskState, WorkspaceTask
    from uni.devcoord.workspace_store import WorkspaceStore
    from uni.webui.handlers.workspace import _workspace_overview

    store = WorkspaceStore(tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite")
    task = WorkspaceTask(id="task-1", title="Improve admin", state=WorkTaskState.VERIFIED,
                         acceptance_items=[AcceptanceItem(key="a", passed=True)])
    session = AgentSession(agent_id="chatgpt", display_name="ChatGPT", task_id=task.id)
    store.save_workspace_task(task); store.save_session(session)
    overview = _workspace_overview(tmp_path)
    assert overview["agents"][0]["name"] == "ChatGPT"
    assert overview["tasks"][0]["status"] == "WAITING OWNER"
    assert overview["tasks"][0]["progress"] == 99
    assert overview["tasks"][0]["owner_verified"] is False


def test_owner_verification_fails_closed_without_mawc_evidence(tmp_path, monkeypatch):
    from uni.devcoord.workspace_models import AcceptanceItem, WorkTaskState, WorkspaceTask
    from uni.devcoord.workspace_store import WorkspaceStore
    import uni.webui.server as srv
    from uni.webui.handlers.workspace import _owner_verification

    store = WorkspaceStore(tmp_path / ".uni-dev" / "coordination" / "workspace.sqlite")
    store.save_workspace_task(WorkspaceTask(id="task-1", title="Verify me", state=WorkTaskState.VERIFIED,
        acceptance_items=[AcceptanceItem(key="a", passed=True)]))
    monkeypatch.setattr(srv, "_ROOT", tmp_path)
    class Handler:
        client_address=("127.0.0.1",50000); path="/api/workspace/tasks/task-1/owner-verification"; response=None
        def _read_json_body(self): return {"verified": True, "note": "Проверено"}
        def _json(self,status,payload): self.response=(status,payload)
    handler=Handler(); _owner_verification(handler)
    assert handler.response[0] == 409
    assert "evidence" in handler.response[1]["error"].lower()
    assert store.get_workspace_task("task-1").owner_verified is False


def test_checkpoint_views_expose_known_good_contract(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import uni.checkpoints as checkpoints
    from uni.checkpoints import CheckpointType
    from uni.webui.handlers.workspace import _checkpoint_views

    item = SimpleNamespace(
        id="cp-1", label="Known Good", created_at="2026-09-12T00:00:00+00:00",
        type=CheckpointType.PROJECT_KNOWN_GOOD, snapshot_ref="git-tree:tree123",
        source_git_revision="commit123", master_revision="master123",
        owner_verified_at="2026-09-12T00:00:00+00:00",
        verified_features=("workspace",), test_evidence=("pytest",),
    )
    class FakeGit:
        def head_revision(self): return "commit123"
        def is_clean(self): return False
    class FakeManager:
        def __init__(self, root): self.git = FakeGit()
        def list_checkpoints(self): return (item,)
    monkeypatch.setattr(checkpoints, "CheckpointManager", FakeManager)

    view = _checkpoint_views(tmp_path)[0]
    assert view["type"] == "project_known_good"
    assert view["master_revision"] == "master123"
    assert view["source_git_revision"] == "commit123"
    assert view["snapshot_ref"] == "git-tree:tree123"
    assert view["verified_features"] == ["workspace"]
