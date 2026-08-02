import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from uni.capabilities.speech import SpeechCapability


class SpeechSynthesisTests(unittest.TestCase):
    def test_local_piper_voice_produces_native_rate_audio(self):
        speech = SpeechCapability(tts_voice="ru_RU-irina-medium.onnx")

        async def synthesize():
            await speech._init_tts()
            return await asyncio.to_thread(speech._synthesize_audio, "Проверка голоса")

        audio, sample_rate = asyncio.run(synthesize())
        self.assertGreater(len(audio), 1000)
        self.assertEqual(sample_rate, 22050)

    def test_silero_adapter_uses_selected_speaker_and_native_rate(self):
        calls = {}

        class FakeSilero:
            def apply_tts(self, **kwargs):
                calls.update(kwargs)
                return np.ones(2400, dtype=np.float32)

        speech = SpeechCapability(
            tts_provider="silero",
            silero_speaker="xenia",
            silero_sample_rate=48000,
        )
        speech._silero = FakeSilero()
        audio, sample_rate = speech._synthesize_audio("Проверка красивого голоса")
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(calls["speaker"], "xenia")
        self.assertEqual(calls["sample_rate"], 48000)
        self.assertEqual(audio.dtype, np.float32)

    def test_selected_voice_exports_wav(self):
        class FakeSilero:
            def apply_tts(self, **_kwargs):
                return np.linspace(-0.2, 0.2, 4800, dtype=np.float32)

        speech = SpeechCapability(tts_provider="silero", silero_sample_rate=48000)
        speech._silero = FakeSilero()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message.wav"
            result = asyncio.run(speech.synthesize_file("Привет", str(path), "wav"))
            self.assertTrue(result.success)
            audio, sample_rate = sf.read(path)
            self.assertEqual(sample_rate, 48000)
            self.assertGreater(len(audio), 1000)

    def test_mp3_reports_missing_ffmpeg(self):
        speech = SpeechCapability()
        with tempfile.TemporaryDirectory() as directory, patch(
            "uni.capabilities.speech.shutil.which", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                speech._write_audio_file(
                    np.zeros(1000, dtype=np.float32),
                    16000,
                    Path(directory) / "message.mp3",
                    "mp3",
                )

    def test_escape_interrupts_chunked_playback(self):
        writes = []

        class FakeOutputStream:
            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def write(self, chunk):
                writes.append(chunk.copy())

        speech = SpeechCapability()
        with patch("uni.capabilities.speech.sd.OutputStream", FakeOutputStream), patch.object(
            speech,
            "_escape_pressed",
            side_effect=[False, True],
        ):
            speech._play(np.ones(1000, dtype=np.float32), 1000)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].shape, (100, 1))
