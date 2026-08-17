"""Тесты извлечённых модулей event_loop (P-06, 2026-08-17).

Эти тесты покрывают логику БЕЗ инстанцирования EventLoop, что решает
проблему «950 строк слишком много для изолированного тестирования».
"""
from __future__ import annotations

import pytest


# ---------- command_parser ----------

def test_parse_help():
    from uni.loops.command_parser import parse_direct_command
    cmd = parse_direct_command("помощь")
    assert cmd is not None and cmd.action == "internal.help"


def test_parse_intensity():
    from uni.loops.command_parser import parse_direct_command
    cmd = parse_direct_command("интенсивность 42")
    assert cmd is not None
    assert cmd.action == "xtoys.set_intensity"
    assert cmd.args["value"] == 42


def test_parse_camera_watch_duration():
    from uni.loops.command_parser import parse_direct_command
    cmd = parse_direct_command("смотри через камеру 10 минут")
    assert cmd is not None
    assert cmd.action == "internal.camera_watch"
    assert cmd.args["seconds"] == 600.0


def test_parse_url():
    from uni.loops.command_parser import parse_direct_command
    cmd = parse_direct_command("открой сайт example.com")
    assert cmd is not None and cmd.action == "browser.navigate"


def test_parse_stop_words():
    from uni.loops.command_parser import is_stop_command
    assert is_stop_command("стоп")
    assert is_stop_command("EXIT")
    assert is_stop_command("  Аварийный СТОП  ")
    assert not is_stop_command("продолжай")


def test_parse_unknown_returns_none():
    from uni.loops.command_parser import parse_direct_command
    assert parse_direct_command("привет как дела") is None


# ---------- visual_router ----------

def test_match_visual_goal():
    from uni.loops.visual_router import match_visual_goal
    assert match_visual_goal("открой блокнот") == "блокнот"
    assert match_visual_goal("кликни на кнопку ОК") == "кнопку ОК"
    assert match_visual_goal("привет") is None
    assert match_visual_goal("") is None


# ---------- screen_watch helpers ----------

def test_is_sensitive_url():
    from uni.loops.screen_watch import is_sensitive_url
    assert is_sensitive_url("https://mail.google.com/mail/u/0/")
    assert is_sensitive_url("https://bank.example.com/account/login")
    assert not is_sensitive_url("https://ru.wikipedia.org/wiki/UNI")


# ---------- i18n ----------

def test_i18n_ru():
    from uni.i18n import set_locale, t
    set_locale("ru")
    assert "Миссия" in t("mission.started")


def test_i18n_en():
    from uni.i18n import set_locale, t
    set_locale("en")
    assert "Mission" in t("mission.started")


def test_i18n_fallback():
    from uni.i18n import set_locale, t
    set_locale("ru")
    # неизвестный ключ -> возвращается как есть
    assert t("non.existent.key") == "non.existent.key"


# ---------- plugins ----------

def test_discover_plugins_includes_core():
    from uni.plugins import discover_plugins
    plugins = discover_plugins()
    names = [p["name"] for p in plugins]
    assert "core" in names


# ---------- secrets ----------

def test_mask_secret():
    from uni.secrets import mask_secret
    assert mask_secret("") == ""
    assert mask_secret("sk-or-ABC123") == "sk-o***C123"
    assert mask_secret("short") == "***"


def test_apply_env_overrides(monkeypatch):
    from uni.secrets import apply_env_overrides
    from uni.config import Config
    monkeypatch.setenv("UNI_BRAIN_API_KEY", "test-key-123")
    cfg = Config()
    applied = apply_env_overrides(cfg)
    assert "UNI_BRAIN_API_KEY" in applied
    assert cfg.brain.api_key == "test-key-123"


# ---------- logging_setup ----------

def test_json_formatter():
    import logging
    from uni.logging_setup import JsonFormatter, with_trace
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello %s", args=("world",), exc_info=None,
    )
    with with_trace("trace-xyz"):
        out = formatter.format(record)
    import json
    data = json.loads(out)
    assert data["message"] == "hello world"
    assert data["trace_id"] == "trace-xyz"
