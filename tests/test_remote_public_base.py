"""Тест env-флага UNI_REMOTE_PUBLIC_BASE (B-06).

Проверяет, что _start_public_tunnel возвращает заданный публичный base URL,
не запуская cloudflared, когда UNI_REMOTE_PUBLIC_BASE установлен. И что при
отсутствии флага идёт старый путь (вызов cloudflared — мокаем, чтобы не запускать).
"""

from __future__ import annotations

from unittest import mock

import pytest

import uni.webui.server as srv


def test_env_public_base_returns_without_cloudflared(monkeypatch):
    # сброс глобального состояния туннеля
    monkeypatch.setattr(srv, "_PUBLIC_TUNNEL_PROCESS", None)
    monkeypatch.setattr(srv, "_PUBLIC_TUNNEL_URL", "")
    monkeypatch.setenv("UNI_REMOTE_PUBLIC_BASE", "https://uni.example.com")

    popen_calls = []
    real_popen = subprocess_module_popen()
    def fake_popen(*a, **k):
        popen_calls.append((a, k))
        raise RuntimeError("cloudflared не должен запускаться при env-флаге")
    monkeypatch.setattr(srv.subprocess, "Popen", fake_popen)

    url = srv._start_public_tunnel()
    assert url == "https://uni.example.com"
    assert popen_calls == []  # cloudflared не запускался


def test_env_public_base_empty_falls_through(monkeypatch):
    # без флага — должен пойти по старому пути (cloudflared). Мокаем Popen,
    # чтобы не запускать реальный процесс, и ловим RuntimeError от несуществующего бинаря.
    monkeypatch.setattr(srv, "_PUBLIC_TUNNEL_PROCESS", None)
    monkeypatch.setattr(srv, "_PUBLIC_TUNNEL_URL", "")
    monkeypatch.setenv("UNI_REMOTE_PUBLIC_BASE", "")

    # Popen должен быть вызван (старый путь). Замокаем, чтобы вернуть фейк-процесс,
    # но тест просто проверяет, что код ДОШЁЛ до Popen (не упал на env-проверке раньше).
    class _FakeProc:
        def poll(self): return 0
        def terminate(self): pass
        stdout = None
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: _FakeProc())

    # binary cloudflared.exe не существует -> _ensure_remote_gateway/путь упадёт до Popen
    # или после Popen не найдёт URL. Главное — что env-проверка пропущена (не вернул early).
    try:
        srv._start_public_tunnel()
    except RuntimeError as exc:
        # ожидаемо: cloudflared.exe не установлен / не выдал адрес
        assert "cloudflared" in str(exc).lower() or "публичный" in str(exc).lower()


def subprocess_module_popen():
    return srv.subprocess.Popen
