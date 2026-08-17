"""Тесты R-очереди: R-01 (маршрут /v3) и R-02 (маскировка секретов в JSON)."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
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


def test_r01_v3_route_redirects_to_supported_admin(server):
    # Единственная поддерживаемая админка доступна через /v4/.
    with urllib.request.urlopen(server + "/v3", timeout=5) as r:
        body = r.read().decode("utf-8")
        assert r.status == 200
        assert r.geturl().endswith("/v4/")
        assert "text/html" in r.headers.get("Content-Type", "")
        assert "admin" in body.lower() or "Юни" in body or "UNI" in body


def test_r02_secret_masked_in_json(server):
    # R-02: если эндпоинт вернёт api_key/sk-, оно маскируется
    # используем /api/config — там api_key_set (уже bool), но проверим маскировку
    # через прямой вызов _sanitize_secrets (юнит)
    sample = {
        "endpoints": {"openrouter": {"api_key": "sk-or-ABCDEFG1234567890secret"}},
        "token": "gsk_xyz1234567890abcdef",
        "nested": [{"secret": "hf_abcdefghijklmnop"}],
        "safe": "обычный текст",
    }
    masked = srv._sanitize_secrets(sample)
    blob = json.dumps(masked)
    assert "sk-or-" not in blob
    assert "gsk_" not in blob
    assert "hf_" not in blob
    assert "***masked***" in blob
    assert masked["safe"] == "обычный текст"


def test_r02_sanitize_idempotent():
    # повторная маскировка не ломает уже замаскированное
    once = srv._sanitize_secrets({"k": "sk-or-ABCDEFG1234567890secret"})
    twice = srv._sanitize_secrets(once)
    assert "sk-or-" not in json.dumps(twice)
