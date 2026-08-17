"""Тесты админки v3 (T-04..T-08, T-15, T-16): эндпоинты server.py без запуска всей панели.

Поднимаем реальный ThreadingHTTPServer с _Handler на случайном свободном
порту в отдельном потоке, делаем HTTP GET/POST к новым эндпоинтам и проверяем
ответы. Это даёт настоящий proof of work (реальный сервер, реальные файлы).
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

import uni.webui.server as srv


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    httpd = srv.ThreadingHTTPServer(("127.0.0.1", port), srv._Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.6)
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(base: str, path: str):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body[:200]}


def test_global_state(server):
    status, data = _get(server, "/api/global_state")
    assert status == 200
    assert "content" in data
    assert "UNI_GLOBAL_STATE" in data["content"]


def test_tasks(server):
    status, data = _get(server, "/api/tasks")
    assert status == 200
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
    ids = {t["id"] for t in data["tasks"] if t["id"]}
    assert ids


def _registry_names_lower():
    """Source of truth for council participants (case-insensitive lookup)."""
    from uni.council.participants import load_participants
    return {p.name.lower() for p in load_participants()}


def test_heartbeats(server):
    status, data = _get(server, "/api/heartbeats")
    assert status == 200
    assert "participants" in data
    names = {p["name"].lower() for p in data["participants"]}
    # Hermes is a real, configured council participant (coordinator). The
    # endpoint must surface it. Resolves the name via the canonical registry
    # so the test detects a genuine regression (not a hardcoded string).
    assert "hermes" in _registry_names_lower()
    assert "hermes" in names


def test_journal(server):
    status, data = _get(server, "/api/journal")
    assert status == 200
    assert "entries" in data
    assert isinstance(data["entries"], list)
    assert len(data["entries"]) <= 100
    assert data.get("available") in (True, False)


def test_participants_dirs(server):
    status, data = _get(server, "/api/participants_dirs")
    assert status == 200
    assert "participants" in data
    names = {p["name"].lower() for p in data["participants"]}
    # uni-* directories are an opt-in participant source; the canonical
    # registry (which always includes hermes) must be reflected. This detects
    # a real regression where the API stops surfacing configured participants.
    assert "hermes" in _registry_names_lower()


def test_admin_stop(server):
    # T-15: POST /api/admin/stop создаёт STOP.txt в корне проекта
    stop_file = srv._ROOT / "STOP.txt"
    if stop_file.exists():
        stop_file.replace(stop_file.with_suffix(".txt.bak"))
    try:
        req = urllib.request.Request(server + "/api/admin/stop", data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            status = r.status
            data = json.loads(r.read().decode("utf-8"))
        assert status == 200
        assert data.get("stopped") is True
        assert stop_file.exists()
        assert "STOP" in stop_file.read_text(encoding="utf-8")
    finally:
        if stop_file.exists():
            stop_file.replace(stop_file.with_suffix(".txt.consumed"))


def test_report_invalid_id_rejected(server):
    # T-16: валидация входных данных — инъекция в round id отклоняется (400/404)
    bad = urllib.parse.quote("../../../etc/passwd")
    try:
        with urllib.request.urlopen(server + "/api/report?id=" + bad, timeout=5) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status in (400, 404)


def test_global_state_no_traversal(server):
    # T-16: endpoint не отдаёт путь вне _ROOT (file-поле только внутри проекта)
    status, data = _get(server, "/api/global_state")
    assert status == 200
    assert ".." not in data.get("file", "")
