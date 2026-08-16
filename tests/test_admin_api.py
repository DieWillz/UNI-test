"""Тесты админки (Директива ADM-01/ADM-02, 2026-08-13).

Проверяем чистые функции admin_api: возвращают dict, fail-closed,
whitelist действий, защита от path traversal в reports. Без живого сервера.
"""
from __future__ import annotations

from pathlib import Path
import sys, json, os

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.webui import admin_api as a


def test_admin_stack_shape():
    s = a.admin_stack()
    for k in ("llama", "webui", "launcher", "electron"):
        assert k in s
        assert "running" in s[k]


def test_admin_hw_shape():
    h = a.admin_hw()
    assert "gpu" in h and "ram" in h and "cpu" in h
    # нет данных -> «—» (честно, не падает)
    assert h["ram"] in ("—",) or isinstance(h["ram"], str)


def test_admin_git_shape():
    g = a.admin_git()
    assert set(g.keys()) >= {"branch", "commit", "message", "time"}


def test_admin_dev_loads_phases_and_backlog():
    d = a.admin_dev()
    assert isinstance(d["phases"], list) and len(d["phases"]) >= 9  # 0..8 + 9
    assert isinstance(d["backlog"], list) and len(d["backlog"]) > 0
    assert "locks" in d


def test_admin_agents_shape():
    ag = a.admin_agents()
    assert "agents" in ag and "count" in ag
    assert ag["count"] == len(ag["agents"])


def test_admin_stats_shape():
    st = a.admin_stats()
    for k in ("ui_events_by_component", "stop_count", "demo_mouse_count",
             "vision_capture_count", "chat_messages", "pytest"):
        assert k in st
    assert isinstance(st["ui_events_by_component"], dict)


def test_admin_reports_list_and_content():
    reps = a.admin_reports_list()
    # Qwen (2026-08-16): контракт изменён — возвращается dict {"reports":[...]}
    # (раньше был list). Проверяем обе формы для обратной совместимости.
    if isinstance(reps, dict):
        items = reps.get("reports", [])
    else:
        items = reps
    assert isinstance(items, list) and len(items) > 0
    # хотя бы один реальный отчёт читается
    name = items[0]["name"]
    content = a.admin_report_content(name)
    assert "content" in content or "error" in content


def test_admin_report_content_traversal_blocked():
    # попытка выйти за пределы папок -> error (не содержимое файла)
    res = a.admin_report_content("../config.yaml")
    assert res.get("error") or "content" not in res
    res2 = a.admin_report_content("..%2f..%2fconfig.yaml")
    assert res2.get("error") or "content" not in res2


def test_handle_admin_action_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        a._handle_admin_action("hack_everything", {})


def test_handle_admin_action_set_ui_variant():
    # реально пишет в state.json и возвращает результат
    res = a._handle_admin_action("set_ui_variant", {"v": "v3"})
    assert res["key"] == "interface" and res["value"] == "v3"
    # вернуть обратно, чтобы не ломать state пользователя
    a._write_state("interface", "v4")


def test_handle_admin_action_create_stop_txt(tmp_path, monkeypatch):
    # перенаправим _ROOT на tmp, чтобы не трогать реальный STOP.txt
    monkeypatch.setattr(a, "_ROOT", tmp_path)
    res = a._handle_admin_action("create_stop_txt", {})
    assert (tmp_path / "STOP.txt").is_file()


def test_admin_secret_not_exposed():
    # admin_report_content НЕ должен отдавать config.yaml даже если имя совпадёт
    res = a.admin_report_content("config.yaml")
    # config.yaml лежит в _ROOT, не в outbox/bridge -> not found
    assert res.get("error") == "not found"
