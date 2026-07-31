"""Speech Capability - Whisper (STT) + Piper (TTS)"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from piper import PiperVoice

from ..capabilities.registry import Capability, ToolSchema


class SpeechCapability(Capability):
    def __init__(self, stt_model: str = "base", tts_voice: str = "ru_RU-irina-medium", sample_rate: int = 16000):
        super().__init__("speech")
        self.stt_model_name = stt_model
        self.tts_voice_name = tts_voice
        self.sample_rate = sample_rate
        self._stt_model: WhisperModel | None = None
        self._tts_voice: PiperVoice | None = None

        self.register_tool(ToolSchema(
            name="listen",
            description="Record audio and transcribe to text",
            parameters={
                "type": "object",
                "properties": {
                    "duration": {"type": "number", "default": 5, "description": "Recording duration in seconds"},
                    "language": {"type": "string", "default": "ru", "description": "Language code"},
                },
            },
        ))
        self.register_tool(ToolSchema(
            name="speak",
            description="Convert text to speech and play",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"},
                    "voice": {"type": "string", "description": "Voice override (optional)"},
                },
                "required": ["text"],
            },
        ))

    async def initialize(self) -> None:
        # Load models in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        self._stt_model = await loop.run_in_executor(None, WhisperModel, self.stt_model_name, "cpu", "int8")
        self._tts_voice = await loop.run_in_executor(None, PiperVoice.load, self.tts_voice_name)

    async def execute(self, tool_name: str, args: dict) -> Any:
        if tool_name == "listen":
            return await self._listen(args.get("duration", 5), args.get("language", "ru"))
        elif tool_name == "speak":
            return await self._speak(args["text"], args.get("voice"))
        raise ValueError(f"Unknown tool: {tool_name}")

    async def _listen(self, duration: float, language: str) -> dict:
        """Record audio and transcribe."""
        loop = asyncio.get_event_loop()

        def record_and_transcribe():
            # Record audio
            recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype="int16")
            sd.wait()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, recording, self.sample_rate)
                temp_path = f.name

            try:
                # Transcribe
                segments, _ = self._stt_model.transcribe(temp_path, language=language, vad_filter=True)
                text = " ".join(seg.text for seg in segments).strip()
                return {"text": text, "success": True}
            finally:
                Path(temp_path).unlink(missing_ok=True)

        return await loop.run_in_executor(None, record_and_transcribe)

    async def _speak(self, text: str, voice: str | None = None) -> dict:
        """Convert text to speech and play."""
        loop = asyncio.get_event_loop()

        def synthesize_and_play():
            tts_voice = self._tts_voice
            if voice and voice != self.tts_voice_name:
                tts_voice = PiperVoice.load(voice)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name

            try:
                # Synthesize
                tts_voice.synthesize(text, temp_path)
                # Play
                data, sr = sf.read(temp_path)
                sd.play(data, sr)
                sd.wait()
                return {"success": True}
            finally:
                Path(temp_path).unlink(missing_ok=True)

        return await loop.run_in_executor(None, synthesize_and_play)