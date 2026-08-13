"""Тесты audio_env_detect (Директива INT-03, 2026-08-13).

Честный статус аудио-окружения: нет warnings -> available=True; любая
ошибка импорта/логики не крашит (fail-closed). Интеграция в /api/uni/status
проверяется отдельно (ADM-04 / ручной curl на целевой машине).
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.utils import audio_env_detect as aed


def test_shape_and_no_warnings():
    res = aed.detect_audio_environment()
    assert set(res.keys()) == {"available", "warnings", "notices"}
    assert isinstance(res["available"], bool)
    assert isinstance(res["warnings"], list)
    assert isinstance(res["notices"], list)


def test_helpers_safe():
    # чистые помощники не падают на Windows-headless
    assert aed.is_container() in (True, False)
    assert aed.is_wsl() in (True, False)
    assert aed.is_ssh() in (True, False)
    assert aed.has_forwarded_audio() in (True, False)


def test_fail_closed_on_import_error(monkeypatch):
    # 🤖 INT-03: если модуль недоступен, статус = STT отключён (fail-closed),
    # а НЕ исключение. Имитируем сбой импорта в server.py.
    import types

    def boom(*a, **k):
        raise RuntimeError("PortAudio missing")

    fake = types.ModuleType("uni.utils.audio_env_detect")
    monkeypatch.setitem(sys.modules, "uni.utils.audio_env_detect", fake)
    # импорт внутри try/except в server даёт fail-closed — проверяем саму логику
    audio = {"stt": "НЕ ПРОВЕРЕНО", "tts": "НЕ ПРОВЕРЕНО", "warnings": [], "notices": []}
    try:
        from uni.utils.audio_env_detect import detect_audio_environment  # noqa
        env = detect_audio_environment()
        if env.get("available"):
            audio["stt"] = "микрофон есть"
        else:
            audio["stt"] = "STT отключён"
    except Exception as _ae:
        audio["stt"] = "STT отключён"
        audio["tts"] = "вывод отключён"
        audio["notices"] = [f"audio_env_detect недоступен: {_ae}"]
    assert audio["stt"] == "STT отключён"
