"""Тесты D-13/D-14: проактивность (детектор событий + бюджет, act whitelist).

Реальный сервер в потоке + юнит-тесты модуля uni.desktop.observe.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request

import pytest

import uni.webui.server as srv
from uni.desktop.observe import detect_event, act_allowed, ACTION_WHITELIST


# --- юнит-тесты модуля observe (без сервера) ---
def test_detect_event():
    assert detect_event("Error: failed to connect") == "error"
    assert detect_event("Do you want to allow access?") == "dialog"
    assert detect_event("waiting for response") == "idle"
    assert detect_event("just some text") is None


def test_act_whitelist():
    assert act_allowed("open_app") is True
    assert act_allowed("hack_the_system") is False
    assert "click_ok" in ACTION_WHITELIST


# --- интеграционные тесты через сервер ---
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


def _post(base, path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.request.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def test_suggest_detects_event(server):
    # D-13: caption с ошибкой -> инициатива (если бюджет не исчерпан)
    status, data = _post(server, "/api/desktop/suggest", {"caption": "Error: disk full"})
    assert status == 200
    assert data["event"] == "error"
    # initiative зависит от бюджета/тихих часов; проверяем структуру
    assert "initiative" in data and "text" in data


def test_act_whitelist_enforced(server):
    # D-14: неизвестное действие -> 403 с перечнем разрешённых
    status, data = _post(server, "/api/desktop/act", {"action": "rm_rf"})
    assert status == 403
    assert isinstance(data.get("allowed"), list) and len(data["allowed"]) > 0
    # Примечание: реальное выполнение разрешённого действия (200/501) требует живого
    # агента (act_on_screen грузит LLM) — не вызываем в тесте, чтобы не висеть.
    # Whitelist-логика покрыта юнит-тестом test_act_whitelist.
