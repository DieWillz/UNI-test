"""Тесты универсального UI-движка (Директива §3: U-02/U-04/U-05/U-06).

Проверяют серверный контракт без запуска HTTP-сервера:
- нормализацию алиасов (progress_task -> task_steps);
- валидацию/очистку компонентов (белый список типов, src только /api|runtime);
- отбрасывание невалидных actions (мёртвых кнопок нет);
- карту действий /api/ui/action (resolve_action) — неизвестный id = ошибка.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.webui.ui_contract import (
    normalize_component, validate_component, validate_ui_events, resolve_action, ACTION_MAP,
)


def test_alias_progress_task_normalized():
    # U-02: алиас progress_task -> task_steps
    assert normalize_component("progress_task") == "task_steps"
    assert normalize_component("gallery") == "result_gallery"
    assert normalize_component("task_steps") == "task_steps"


def test_unknown_component_falls_back_to_result_text():
    c = validate_component({"component": "evil_xss", "text": "<img src=x onerror=alert(1)>"})
    assert c["component"] == "result_text"
    # HTML строка не исполняется (фронт рендерит textContent) — остаётся как текст,
    # но тип безопасен.
    assert "<img" in c["text"]


def test_src_only_local_allowed():
    # внешний url блокируется (ключ src отсутствует)
    bad = validate_component({"component": "result_gallery",
                              "items": [{"image_url": "https://evil.com/a.png", "title": "x"}]})
    assert "src" not in bad["items"][0]
    assert bad["items"][0]["title"] == "x"
    # локальный /api разрешён
    good = validate_component({"component": "result_gallery",
                               "items": [{"image_url": "/api/vision/asset/1", "title": "y"}]})
    assert good["items"][0]["src"] == "/api/vision/asset/1"


def test_dead_buttons_rejected():
    # action вне карты -> отбрасывается (U-05: мёртвых кнопок нет)
    c = validate_component({"component": "result_gallery",
                            "actions": [{"id": "open_all"}, {"id": "pwn_the_world"}]})
    ids = [a["id"] for a in c.get("actions", [])]
    assert "open_all" in ids
    assert "pwn_the_world" not in ids


def test_approval_requires_confirmation_flag_preserved():
    ev = validate_ui_events([{
        "type": "approval.required",
        "title": "Подтвердите рассылку",
        "text": "Клиенту уйдёт письмо",
        "actions": [{"id": "approve"}, {"id": "reject"}],
    }])
    assert ev[0]["type"] == "approval.required"
    assert {a["id"] for a in ev[0]["actions"]} == {"approve", "reject"}


def test_unknown_event_type_dropped():
    ev = validate_ui_events([
        {"type": "task.verified", "task_id": "t1", "verification": {"status": "verified", "method": "test", "evidence": [{"kind": "assertion", "value": "ok"}]}, "ui": {"component": "result_text", "text": "ok"}},
        {"type": "dogSearch.hack", "ui": {"component": "result_gallery"}},  # не канон
    ])
    assert len(ev) == 1
    assert ev[0]["type"] == "task.verified"


def test_resolve_action_known_and_unknown():
    ok = resolve_action("approve", "task_1")
    assert ok["ok"] is True and ok["handler"] == "mission.approve"
    bad = resolve_action("format_c:", None)
    assert bad["ok"] is False and "unknown" in bad.get("error", "")


def test_canon_components_complete():
    # U-03: все 9 канон-компонентов присутствуют в белом списке
    from uni.webui.ui_contract import CANON_COMPONENTS
    for comp in ("task_steps", "result_text", "result_gallery", "result_list",
                 "comparison_table", "mission_card", "approval_required", "form", "link_list"):
        assert comp in CANON_COMPONENTS
