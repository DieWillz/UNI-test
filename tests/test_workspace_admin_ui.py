from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "uni" / "webui" / "index.html"
WORKSPACE_JS = ROOT / "uni" / "webui" / "js" / "workspace.js"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _script() -> str:
    return WORKSPACE_JS.read_text(encoding="utf-8")


def test_one_development_workspace_section_replaces_duplicate_task_page():
    html = _html()
    assert 'data-page="workspace"' in html
    assert "Разработка / Workspace" in html
    assert 'data-page="tasks"' not in html
    assert "Workspace Coordinator" not in html
    assert "Задачи и процессы" not in html


def test_agent_name_task_and_progress_have_dedicated_rendering():
    html, script = _html(), _script()
    assert 'id="workspaceAgents"' in html
    assert 'id="workspaceTasks"' in html
    assert "agent.display_name || agent.name || agent.agent_id" in script
    assert "task.title || task.name || task.id" in script
    assert "displayProgress(task)" in script


def test_stale_state_is_rendered_for_agents_and_tasks():
    script = _script()
    assert "'STALE'" in script
    assert "isStale" in script
    assert "revisionState" in script


def test_last_update_is_visible():
    html, script = _html(), _script()
    assert 'id="workspaceLastUpdate"' in html
    assert "Последнее обновление" in script
    assert "updated_at" in script


def test_waiting_owner_review_has_dedicated_panel():
    html, script = _html(), _script()
    assert 'id="workspaceOwnerReview"' in html
    assert "WAITING OWNER" in script
    assert "ownerReviewHtml" in script


def test_owner_verify_controls_and_note_field_exist():
    script = _script()
    assert "Проверил — работает" in script
    assert "Проверил — не работает" in script
    assert "owner-verification" in script
    assert "ownerReviewNote" in script


def test_progress_never_displays_100_before_owner_verification():
    script = _script()
    assert "function displayProgress(task)" in script
    assert "task.owner_verified === true" in script
    assert "Math.min(99" in script


def test_known_good_and_checkpoint_history_are_rendered():
    html, script = _html(), _script()
    assert 'id="workspaceKnownGood"' in html
    assert 'id="workspaceCheckpointHistory"' in html
    assert "Current Known Good" in script
    assert "checkpointHistoryHtml" in script


def test_restore_is_prepare_plan_not_destructive_rollback():
    html, script = _html(), _script()
    assert 'id="workspaceRestorePlan"' in html
    assert "Подготовить восстановление" in script
    assert "restore-plan" in script
    assert "git reset" not in script.lower()
    assert "git checkout" not in script.lower()


def test_workspace_adapter_prefers_new_overview_api_and_keeps_live_legacy_fallback():
    script = _script()
    assert "workspaceDataAdapter" in script
    assert "/api/workspace/overview" in script
    assert "/api/admin/workspace" in script
    assert "fixture" not in script.lower()


def test_known_good_ui_understands_checkpoint_manager_contract():
    script = _script()
    assert "project_known_good" in script
    assert "source_git_revision" in script
    assert "snapshot_ref" in script
    assert "changed_files" in script
    assert "files_that_would_be_removed" in script
    assert "safe_target_workspace" in script


def test_workspace_ui_matches_normalized_backend_field_names():
    script = _script()
    assert "body:JSON.stringify({verified:ownerVerified===true" in script
    assert "agent.task" in script
    assert "agent.owned_paths" in script
    assert "agent.ack_revision" in script
    assert "revisionState" in script
    assert "current?.reference" in script
    assert "c.reference" in script
