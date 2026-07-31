import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

from uni.capabilities.speech import SpeechCapability


class SpeechInputTests(unittest.TestCase):
    def test_stt_runtime_target_is_passed_to_faster_whisper(self):
        speech = SpeechCapability(
            stt_model="small",
            stt_device="cuda",
            stt_compute_type="float16",
        )
        with patch("uni.capabilities.speech.WhisperModel", return_value=object()) as model:
            asyncio.run(speech._init_stt())
        model.assert_called_once_with("small", device="cuda", compute_type="float16")

    def test_invalid_stt_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cpu или cuda"):
            SpeechCapability(stt_device="tpu")

    def test_transcription_uses_configured_beam_size(self):
        calls = {}

        class Segment:
            text = " распознано "

        class FakeWhisper:
            def transcribe(self, _audio, **kwargs):
                calls.update(kwargs)
                return [Segment()], object()

        speech = SpeechCapability(stt_beam_size=5)
        speech._whisper = FakeWhisper()
        result = speech._transcribe_audio(np.ones(160, dtype=np.float32))
        self.assertEqual(result, "распознано")
        self.assertEqual(calls["beam_size"], 5)

    def test_gain_removes_dc_offset_and_amplifies(self):
        speech = SpeechCapability(microphone_gain=5.0)
        audio = np.array([0.11, 0.09, 0.11, 0.09], dtype=np.float32)
        prepared = speech._prepare_input_audio(audio)
        np.testing.assert_allclose(prepared, [0.05, -0.05, 0.05, -0.05], atol=1e-6)
        self.assertEqual(prepared.dtype, np.float32)

    def test_gain_clips_to_valid_float_audio_range(self):
        speech = SpeechCapability(microphone_gain=5.0)
        prepared = speech._prepare_input_audio(np.array([-0.5, 0.0, 0.5], dtype=np.float32))
        np.testing.assert_array_equal(prepared, [-1.0, 0.0, 1.0])

    def test_gain_is_bounded_in_runtime_adapter(self):
        self.assertEqual(SpeechCapability(microphone_gain=100.0).microphone_gain, 20.0)
        self.assertEqual(SpeechCapability(microphone_gain=0.0).microphone_gain, 0.1)

    def test_silence_detection_uses_amplified_signal(self):
        speech = SpeechCapability(microphone_gain=5.0)
        speech._whisper = object()
        quiet_but_usable = np.array([-0.0006, 0.0006] * 100, dtype=np.float32)
        speech._record_utterance = lambda _duration: quiet_but_usable
        speech._transcribe_audio = lambda audio: "услышано" if np.max(np.abs(audio)) > 0.002 else ""
        with patch.object(speech, "_init_stt", new=AsyncMock()):
            result = asyncio.run(speech.listen(0.5))
        self.assertEqual(result, "услышано")

    def test_voice_activated_recording_stops_after_trailing_pause(self):
        speech = SpeechCapability(
            microphone_gain=5.0,
            voice_activation_threshold=0.004,
            voice_silence_seconds=0.2,
        )
        blocksize = int(speech.sample_rate * 0.1)
        silence = np.zeros((blocksize, 1), dtype=np.float32)
        voice = np.tile(np.array([[-0.002], [0.002]], dtype=np.float32), (blocksize // 2, 1))
        chunks = [silence, voice, voice, silence, silence]

        class FakeStream:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _blocksize):
                return chunks.pop(0), False

        with patch("uni.capabilities.speech.sd.InputStream", return_value=FakeStream()):
            recorded = speech._record_utterance(1.0)
        self.assertEqual(len(recorded), blocksize * 5)
        self.assertTrue(np.any(recorded))

    def test_known_subtitle_hallucination_is_rejected(self):
        class Segment:
            text = "Редактор субтитров Н. Закомолдина Корректор А. Егорова"
            no_speech_prob = 0.1
            avg_logprob = -0.2
            compression_ratio = 1.0

        class FakeWhisper:
            def transcribe(self, _audio, **_kwargs):
                return [Segment()], object()

        speech = SpeechCapability()
        speech._whisper = FakeWhisper()
        self.assertEqual(speech._transcribe_audio(np.ones(160, dtype=np.float32)), "")


if __name__ == "__main__":
    unittest.main()
