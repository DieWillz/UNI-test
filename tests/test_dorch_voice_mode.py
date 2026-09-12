from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from uni.capabilities.speech import SpeechCapability
from uni.control_queue import ControlQueue
from uni.webui import chat_support


class FakeCoordinator:
    def __init__(self):
        self.calls = []
        self.current_value = 0
        self.emergency_stopped = False

    async def set_intensity(self, source, value):
        self.calls.append(("set", source, int(value)))
        self.current_value = int(value)
        return True

    async def release(self, source):
        self.calls.append(("release", source))
        self.current_value = 0

    async def emergency_stop(self):
        self.calls.append(("emergency",))
        self.emergency_stopped = True
        self.current_value = 0
        return True


def test_polite_timed_power_request_is_parsed():
    request = chat_support.power_request("а вы можете включить мощность 50% на 30 секунд?")
    assert request == {"value": 50, "duration_seconds": 30.0}


@pytest.mark.asyncio
async def test_manual_hold_acknowledges_transport_and_zeros_after_duration():
    coordinator = FakeCoordinator()
    queue = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)

    result = await queue.manual_hold(50, 0.05, speech="Держу 50 процентов.")

    assert result["accepted"] is True
    assert result["transport_acknowledged"] is True
    assert coordinator.calls[0] == ("set", "manual", 50)
    await asyncio.sleep(0.09)
    assert coordinator.current_value == 0
    assert ("release", "manual") in coordinator.calls
    assert queue.status()["mode"] == "stopped"


@pytest.mark.asyncio
async def test_graceful_pause_does_not_latch_emergency_stop():
    coordinator = FakeCoordinator()
    queue = ControlQueue(coordinator=coordinator, max_intensity=65, allowed=lambda: True)
    await queue.manual_hold(20, 1.0)

    await queue.pause()

    assert coordinator.emergency_stopped is False
    assert queue.status()["mode"] == "stopped"
    assert queue.status()["emergency_stop"] is False
    assert coordinator.current_value == 0


@pytest.mark.asyncio
async def test_media_stt_uses_russian_and_configured_beam(tmp_path):
    seen = {}

    class Segment:
        text = " Привет, Юни "
        no_speech_prob = 0.01
        avg_logprob = -0.1
        compression_ratio = 1.0

    class Whisper:
        def transcribe(self, path, **kwargs):
            seen.update(kwargs)
            assert str(path).endswith(".webm")
            return [Segment()], object()

    speech = SpeechCapability(stt_model="small", stt_device="cpu", stt_compute_type="int8", stt_beam_size=5)
    speech._whisper = Whisper()
    text = await speech.transcribe_media_bytes(b"synthetic-audio", "audio/webm")

    assert text == "Привет, Юни"
    assert seen["language"] == "ru"
    assert seen["beam_size"] == 5
    assert seen["vad_filter"] is True


def test_main_chat_uses_local_stt_and_has_continuous_dialog_mode():
    from pathlib import Path

    webui = Path(__file__).resolve().parents[1] / "uni" / "webui"
    html = (webui / "index.html").read_text(encoding="utf-8")
    js = (webui / "js" / "chat-controls.js").read_text(encoding="utf-8")

    assert 'value="dialog"' in html
    assert "/api/stt/listen" in js
    assert "SpeechRecognition" not in js
    assert "webkitSpeechRecognition" not in js
    assert "dialogListening" in js


def test_webui_exposes_server_side_listen_endpoint_and_dorch_auto_toggle():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    server = (root / "uni" / "webui" / "server.py").read_text(encoding="utf-8")
    html = (root / "uni" / "webui" / "index.html").read_text(encoding="utf-8")
    js = (root / "uni" / "webui" / "js" / "chat-controls.js").read_text(encoding="utf-8")

    assert 'self.path == "/api/stt/listen"' in server
    assert "speech.listen" in server
    assert 'id="dorchAutoBtn"' in html
    assert "toggleDorchAuto" in js
    assert "/api/xtoys/autonomous/stop" in js
