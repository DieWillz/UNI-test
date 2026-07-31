import asyncio
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from piper import PiperVoice
from uni.contracts import ToolResult
from .base import Capability

class SpeechCapability(Capability):
    name = "speech"
    description = "Распознавание и синтез речи"

    def __init__(self, stt_model: str = "base", tts_voice: str = "ru_RU-irina-medium", sample_rate: int = 16000):
        self.stt_model = stt_model
        self.tts_voice = tts_voice
        self.sample_rate = sample_rate
        self._whisper = None
        self._piper = None

    async def _init_stt(self):
        if self._whisper is None:
            self._whisper = WhisperModel(self.stt_model, device="cpu", compute_type="int8")

    async def _init_tts(self):
        if self._piper is None:
            self._piper = PiperVoice.load(self.tts_voice)

    async def listen(self, duration: int = 5) -> str:
        await self._init_stt()
        audio = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype=np.float32)
        sd.wait()
        audio_int16 = (audio * 32767).astype(np.int16).flatten()
        segments, _ = await asyncio.to_thread(self._whisper.transcribe, audio_int16, language="ru")
        text = " ".join([seg.text for seg in segments])
        return text.strip()

    async def speak(self, text: str) -> bool:
        try:
            await self._init_tts()
            audio = await asyncio.to_thread(self._piper.synthesize, text)
            sd.play(audio, samplerate=self.sample_rate)
            sd.wait()
            return True
        except Exception as e:
            print(f"TTS error: {e}")
            return False

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "listen":
            duration = kwargs.get("duration", 5)
            text = await self.listen(duration)
            if text:
                return ToolResult(success=True, data=text, message=f"Распознано: {text[:50]}")
            return ToolResult(success=False, message="Речь не распознана")
        elif action == "speak":
            text = kwargs.get("text", "")
            if not text:
                return ToolResult(success=False, message="Нет текста")
            success = await self.speak(text)
            if success:
                return ToolResult(success=True, message="Речь воспроизведена")
            return ToolResult(success=False, message="Ошибка TTS")
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
