from __future__ import annotations

from pathlib import Path

import pytest

from uni.webui import server


def test_tts_payload_is_bounded_and_normalized():
    payload = server._tts_payload(
        {
            "provider": "silero",
            "voice": "baya",
            "text": "  Привет  ",
            "rate": 99,
            "pitch": -99,
            "volume": "0.75",
        }
    )

    assert payload == {
        "provider": "silero",
        "voice": "baya",
        "text": "Привет",
        "rate": 2.0,
        "pitch": -12.0,
        "volume": 0.75,
        "endpoint": "",
        "qwen_ref_audio": "",
        "qwen_ref_text": "",
        "qwen_model_size": "1.7B",
        "qwen_seed": 1800013838,
    }


def test_tts_payload_rejects_unknown_provider_and_empty_text():
    with pytest.raises(ValueError, match="unknown TTS provider"):
        server._tts_payload({"provider": "imaginary", "text": "hello"})
    with pytest.raises(ValueError, match="text required"):
        server._tts_payload({"provider": "silero", "text": " "})


def test_recommended_voice_catalog_is_exposed():
    silero = {voice["id"] for voice in server._TTS_VOICES["silero"]}
    assert {"xenia", "kseniya", "baya", "eugene", "aidar"} <= silero
    assert {"piper", "browser", "xtts", "fish"} <= set(server._TTS_VOICES)


def test_chat_javascript_plays_tts_response_and_surfaces_errors():
    js = (Path(server.__file__).parent / "js" / "app.js").read_text(encoding="utf-8")
    assert "await r.json()" in js
    assert "new URL(d.audio_url,HRM).href" in js
    assert "await _ttsAudio.play()" in js
    assert "if(!r.ok)throw new Error" in js
    assert "showToast('❌ TTS: '" in js


def test_tts_panel_contains_controls_and_optional_engines():
    html = (Path(server.__file__).parent / "index.html").read_text(encoding="utf-8")
    for element_id in (
        "ttsProvider",
        "ttsVoice",
        "ttsEndpoint",
        "ttsRate",
        "ttsPitch",
        "ttsVolume",
        "ttsTestText",
    ):
        assert f'id="{element_id}"' in html
    assert 'value="xtts"' in html
    assert 'value="fish"' in html
