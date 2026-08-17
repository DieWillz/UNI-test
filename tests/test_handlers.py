"""Тесты новых handlers (P-03/07/09/13/16, 2026-08-17)."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest

import uni.webui.server as srv
from uni.webui.handlers import events, memory_facts


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


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(base, path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# ---------- health ----------

def test_health_endpoint_exists(server):
    """GET /api/uni/health должен отвечать (registry зарегистрирован)."""
    status, data = _get(server, "/api/uni/health")
    assert status == 200
    assert "ok" in data and "components" in data and "summary" in data
    # базовая структура
    for key in ("llama", "webui", "memory", "config"):
        assert key in data["components"]


# ---------- memory facts ----------

def test_memory_facts_extraction_rule_based():
    from uni.webui.handlers.memory_facts import extract_facts_from_text
    facts = extract_facts_from_text("меня зовут Иван. я живу в Москве.")
    assert any(f["predicate"] == "имя" and "Иван" in f["object"] for f in facts)
    assert any(f["predicate"] == "живёт в" and "Москв" in f["object"] for f in facts)


def test_memory_facts_endpoint_exists(server):
    status, data = _get(server, "/api/memory/facts")
    assert status == 200
    assert "facts" in data and "count" in data


# ---------- mission ----------

def test_mission_current_endpoint_exists(server):
    status, data = _get(server, "/api/mission/current")
    assert status == 200
    assert "active" in data


def test_mission_lifecycle(server):
    # start
    status, data = _post(server, "/api/mission/start", {"goal": "test mission"})
    assert status == 200 and data["ok"]
    assert data["mission"]["goal"] == "test mission"
    # step
    status, data = _post(server, "/api/mission/step", {"progress_pct": 50})
    assert status == 200 and data["mission"]["progress_pct"] == 50
    # Завершение без evidence обязано fail-closed остаться not_verified.
    status, data = _post(server, "/api/mission/complete", {})
    assert status == 409 and data["status"] == "not_verified"
    # complete with independent evidence
    status, data = _post(server, "/api/mission/complete", {
        "verification": {
            "status": "verified",
            "method": "test_read_after_write",
            "reason": "postcondition checked",
            "evidence": [{
                "source": "tests.test_handlers",
                "summary": "mission postcondition observed",
            }],
        }
    })
    assert status == 200 and data["mission"]["active"] is False
    assert data["mission"]["status"] == "verified"


def test_mission_confirm_income_fail_closed(server):
    _post(server, "/api/mission/start", {"goal": "income test"})
    # отрицательная сумма должна быть отклонена
    status, data = _post(server, "/api/mission/confirm_income", {"amount": -10})
    assert status == 400
    # положительная — принята
    status, data = _post(server, "/api/mission/confirm_income", {"amount": 100, "source": "test"})
    assert status == 200 and data["mission"]["confirmed_income"] == 100


# ---------- event hub ----------

def test_event_hub_publish_subscribe():
    from uni.webui.handlers import events
    q = events.subscribe()
    try:
        events.publish_event({"type": "test", "value": 42})
        event = q.get(timeout=2)
        assert event["type"] == "test" and event["value"] == 42
    finally:
        events.unsubscribe(q)


# ---------- plugins ----------

def test_plugins_endpoint_exists(server):
    status, data = _get(server, "/api/plugins")
    assert status == 200
    assert "plugins" in data
    # хотя бы "core" должен быть
    names = [p["name"] for p in data["plugins"]]
    assert "core" in names
