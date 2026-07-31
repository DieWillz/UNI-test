from __future__ import annotations

import asyncio
import ctypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from piper import PiperVoice

from uni.contracts import ToolResult
from .base import Capability


class SpeechCapability(Capability):
    name = "speech"
    description = "Локальное распознавание и синтез русской речи"

    def __init__(
        self,
        stt_model: str = "base",
        stt_device: str = "cpu",
        stt_compute_type: str = "int8",
        stt_beam_size: int = 1,
        microphone_gain: float = 1.0,
        voice_activation_threshold: float = 0.004,
        voice_silence_seconds: float = 0.8,
        max_utterance_seconds: float = 8.0,
        tts_provider: str = "piper",
        tts_voice: str = "ru_RU-irina-medium.onnx",
        silero_model: str = "v5_5_ru",
        silero_speaker: str = "xenia",
        silero_sample_rate: int = 48000,
        sample_rate: int = 16000,
        input_device: int | str | None = None,
        output_device: int | str | None = None,
    ) -> None:
        self.stt_model = stt_model
        self.stt_device = stt_device.casefold().strip()
        self.stt_compute_type = stt_compute_type.casefold().strip()
        if self.stt_device not in {"cpu", "cuda"}:
            raise ValueError("stt_device должен быть cpu или cuda")
        if not self.stt_compute_type:
            raise ValueError("stt_compute_type не может быть пустым")
        self.stt_beam_size = max(1, min(int(stt_beam_size), 5))
        self.microphone_gain = max(0.1, min(float(microphone_gain), 20.0))
        self.voice_activation_threshold = max(0.0005, min(float(voice_activation_threshold), 0.2))
        self.voice_silence_seconds = max(0.2, min(float(voice_silence_seconds), 3.0))
        self.max_utterance_seconds = max(2.0, min(float(max_utterance_seconds), 30.0))
        self.tts_provider = tts_provider.lower().strip()
        self.tts_voice = self._resolve_voice(tts_voice)
        self.silero_model = silero_model
        self.silero_speaker = silero_speaker
        self.silero_sample_rate = silero_sample_rate
        self.sample_rate = sample_rate
        self.input_device = input_device
        self.output_device = output_device
        self._session_logger = None
        self._whisper: WhisperModel | None = None
        self._piper: PiperVoice | None = None
        self._silero = None
        self._stt_lock = asyncio.Lock()
        self._tts_lock = asyncio.Lock()

    @staticmethod
    def _resolve_voice(value: str) -> str:
        candidate = Path(value)
        project_root = Path(__file__).resolve().parents[2]
        candidates = [candidate, project_root / candidate]
        if candidate.suffix != ".onnx":
            candidates.extend([candidate.with_suffix(".onnx"), (project_root / candidate).with_suffix(".onnx")])
        for path in candidates:
            if path.exists():
                return str(path.resolve())
        return value

    # --- TTS text normalization (Feature C) ---------------------------------
    _EMOJI_RE = re.compile(
        "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
        "\U0000FE00-\U0000FE0F\U0000200D\u2066-\u2069\u2b00-\u2bff]",
        re.UNICODE,
    )
    _URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    _MARKDOWN_RE = re.compile(r"[*_`#>~\[\](){}|]", re.UNICODE)

    @classmethod
    def _clean_for_tts(cls, text: str) -> str:
        """Make text safe for Piper/Silero phonemization.

        Drops emoji, variation selectors, zero-width joiners, Markdown markup
        and control characters; turns URLs into a spoken placeholder; keeps
        Russian/Latin letters, digits and minimal punctuation.
        """
        if not text:
            return ""
        text = unicodedata.normalize("NFKC", text)
        text = cls._EMOJI_RE.sub(" ", text)
        text = cls._URL_RE.sub(" ссылка ", text)
        text = cls._MARKDOWN_RE.sub("", text)
        # keep only allowed characters
        allowed = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat[0] == "C" and ch not in ("\n", "\t"):
                continue
            if ch.isalnum() or ch in " .,!?-—…«»\n\t":
                allowed.append(ch)
            else:
                allowed.append(" ")
        cleaned = "".join(allowed)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or " "

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?…])\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def _synthesize_chunk(self, chunk: str) -> tuple[np.ndarray, int]:
        """Synthesize one sentence; raises on failure."""
        if self.tts_provider == "silero":
            if self._silero is None:
                raise RuntimeError("Silero не загружен")
            audio = self._silero.apply_tts(
                text=chunk,
                speaker=self.silero_speaker,
                sample_rate=self.silero_sample_rate,
            )
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            return np.asarray(audio, dtype=np.float32).reshape(-1), self.silero_sample_rate
        assert self._piper is not None
        frames = list(self._piper.synthesize(chunk))
        if not frames:
            raise RuntimeError("Piper не вернул аудио")
        rates = {f.sample_rate for f in frames}
        if len(rates) != 1:
            raise RuntimeError(f"Piper вернул несколько sample rate: {sorted(rates)}")
        audio = np.concatenate([f.audio_float_array.reshape(-1) for f in frames]).astype(np.float32)
        return audio, frames[0].sample_rate

    def _synthesize_audio_safe(self, text: str) -> tuple[np.ndarray, int]:
        """Clean text, then synthesize sentence-by-sentence.

        A failing sentence is logged and skipped instead of aborting the whole
        utterance (partial success). Returns concatenated (audio, sample_rate).
        """
        cleaned = self._clean_for_tts(text)
        sentences = self._split_sentences(cleaned)
        if not sentences:
            sentences = [cleaned]
        chunks: list[np.ndarray] = []
        rate = self.silero_sample_rate if self.tts_provider == "silero" else 48000
        for sentence in sentences:
            try:
                audio, rate = self._synthesize_chunk(sentence)
                chunks.append(audio)
            except Exception as exc:  # partial success on bad fragment
                if self._log is not None:
                    self._log("TTS_SKIP", f"Пропущен фрагмент TTS: {exc} | текст: {sentence[:80]}")
                else:
                    print(f"TTS skip: {exc}")
        if not chunks:
            raise RuntimeError("Не удалось синтезировать ни одного фрагмента")
        return np.concatenate(chunks).astype(np.float32), rate

    @property
    def _log(self):
        return getattr(self, "_session_logger", None)

    async def _init_stt(self) -> None:
        if self._whisper is None:
            async with self._stt_lock:
                if self._whisper is None:
                    self._whisper = await asyncio.to_thread(
                        WhisperModel,
                        self.stt_model,
                        device=self.stt_device,
                        compute_type=self.stt_compute_type,
                    )

    async def _init_tts(self) -> None:
        if self.tts_provider == "silero" and self._silero is None:
            async with self._tts_lock:
                if self._silero is None:
                    try:
                        self._silero = await asyncio.to_thread(self._load_silero)
                    except Exception as exc:
                        print(f"Silero unavailable, falling back to Piper: {exc}")
                        self.tts_provider = "piper"
                        if self._piper is None:
                            self._piper = await asyncio.to_thread(PiperVoice.load, self.tts_voice)
            return
        if self.tts_provider == "piper" and self._piper is None:
            async with self._tts_lock:
                if self._piper is None:
                    self._piper = await asyncio.to_thread(PiperVoice.load, self.tts_voice)
            return
        if self.tts_provider not in {"piper", "silero"}:
            raise ValueError(f"Неизвестный TTS provider: {self.tts_provider}")

    def _load_silero(self):
        import torch

        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2))))
        cache_dir = Path.home() / ".cache" / "uni" / "silero"
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path = cache_dir / f"{self.silero_model}.pt"
        if not model_path.exists():
            url = f"https://models.silero.ai/models/tts/ru/{self.silero_model}.pt"
            torch.hub.download_url_to_file(url, str(model_path), progress=True)
        model = torch.package.PackageImporter(str(model_path)).load_pickle("tts_models", "model")
        model.to(torch.device("cpu"))
        return model

    async def warmup(self) -> None:
        """Load speech models before the first interactive utterance."""
        await asyncio.gather(self._init_stt(), self._init_tts())

    def _record(self, duration: float) -> np.ndarray:
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            device=self.input_device,
        )
        sd.wait()
        return audio.reshape(-1)

    def _chunk_has_voice(self, audio: np.ndarray) -> bool:
        prepared = self._prepare_input_audio(audio)
        if prepared.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(prepared), dtype=np.float64)))
        return rms >= self.voice_activation_threshold

    def _record_utterance(self, start_timeout: float) -> np.ndarray:
        """Wait for speech, preserve pre-roll, and stop after a trailing pause."""
        chunk_seconds = 0.1
        blocksize = max(1, int(self.sample_rate * chunk_seconds))
        pre_roll: deque[np.ndarray] = deque(maxlen=3)
        utterance: list[np.ndarray] = []
        started = False
        silent_chunks = 0
        required_silent_chunks = max(1, round(self.voice_silence_seconds / chunk_seconds))
        wait_deadline = time.monotonic() + max(0.5, float(start_timeout))
        utterance_deadline = float("inf")

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            device=self.input_device,
            blocksize=blocksize,
        ) as stream:
            while True:
                chunk, overflowed = stream.read(blocksize)
                if overflowed:
                    continue
                mono = np.asarray(chunk, dtype=np.float32).reshape(-1).copy()
                has_voice = self._chunk_has_voice(mono)
                now = time.monotonic()
                if not started:
                    pre_roll.append(mono)
                    if has_voice:
                        started = True
                        utterance.extend(pre_roll)
                        pre_roll.clear()
                        utterance_deadline = now + self.max_utterance_seconds
                    elif now >= wait_deadline:
                        return np.empty(0, dtype=np.float32)
                    continue

                utterance.append(mono)
                silent_chunks = 0 if has_voice else silent_chunks + 1
                if silent_chunks >= required_silent_chunks or now >= utterance_deadline:
                    break

        return np.concatenate(utterance).astype(np.float32, copy=False) if utterance else np.empty(0, dtype=np.float32)

    def _prepare_input_audio(self, audio: np.ndarray) -> np.ndarray:
        """Remove DC offset, amplify, and hard-limit audio for Whisper."""
        prepared = np.asarray(audio, dtype=np.float32).reshape(-1)
        if prepared.size == 0:
            return prepared
        prepared = prepared - np.mean(prepared, dtype=np.float64)
        prepared = prepared * self.microphone_gain
        return np.clip(prepared, -1.0, 1.0).astype(np.float32, copy=False)

    async def listen(self, duration: float = 4.0) -> str:
        await self._init_stt()
        recorded = await asyncio.to_thread(self._record_utterance, max(0.5, float(duration)))
        audio = self._prepare_input_audio(recorded)
        if float(np.max(np.abs(audio), initial=0.0)) < 0.002:
            return ""
        assert self._whisper is not None
        return await asyncio.to_thread(self._transcribe_audio, audio)

    def _transcribe_audio(self, audio: np.ndarray) -> str:
        assert self._whisper is not None
        segments, _ = self._whisper.transcribe(
            audio,
            language="ru",
            beam_size=self.stt_beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        accepted: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            if float(getattr(segment, "no_speech_prob", 0.0)) > 0.65:
                continue
            if float(getattr(segment, "avg_logprob", 0.0)) < -1.2:
                continue
            if float(getattr(segment, "compression_ratio", 0.0)) > 2.4:
                continue
            accepted.append(text)
        transcript = " ".join(accepted).strip()
        normalized = " ".join(transcript.casefold().split())
        hallucination_markers = (
            "редактор субтитров",
            "корректор а.",
            "корректор н.",
            "субтитры сделал",
            "субтитры создавал",
            "продолжение следует",
        )
        if any(marker in normalized for marker in hallucination_markers):
            return ""
        return transcript

    def _synthesize_audio(self, text: str) -> tuple[np.ndarray, int]:
        if self.tts_provider == "silero":
            if self._silero is None:
                raise RuntimeError("Silero не загружен")
            audio = self._silero.apply_tts(
                text=text,
                speaker=self.silero_speaker,
                sample_rate=self.silero_sample_rate,
            )
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            return np.asarray(audio, dtype=np.float32).reshape(-1), self.silero_sample_rate
        assert self._piper is not None
        chunks = list(self._piper.synthesize(text))
        if not chunks:
            raise RuntimeError("Piper не вернул аудио")
        sample_rates = {chunk.sample_rate for chunk in chunks}
        if len(sample_rates) != 1:
            raise RuntimeError(f"Piper вернул несколько sample rate: {sorted(sample_rates)}")
        audio = np.concatenate([chunk.audio_float_array.reshape(-1) for chunk in chunks]).astype(np.float32)
        return audio, chunks[0].sample_rate

    @staticmethod
    def _escape_pressed() -> bool:
        if os.name != "nt":
            return False
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)

    def _play(self, audio: np.ndarray, sample_rate: int) -> None:
        chunk_frames = max(1, int(sample_rate * 0.1))
        with sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype=np.float32,
            device=self.output_device,
        ) as stream:
            for offset in range(0, len(audio), chunk_frames):
                if self._escape_pressed():
                    break
                chunk = np.asarray(audio[offset : offset + chunk_frames], dtype=np.float32).reshape(-1, 1)
                stream.write(chunk)

    async def speak(self, text: str) -> bool:
        if not text.strip():
            return False
        try:
            await self._init_tts()
            audio, sample_rate = await asyncio.to_thread(self._synthesize_audio_safe, text.strip())
            await asyncio.to_thread(self._play, audio, sample_rate)
            return True
        except Exception as exc:
            if self._log is not None:
                self._log("TTS_ERROR", str(exc))
            else:
                print(f"TTS error: {exc}")
            return False

    def _write_audio_file(self, audio: np.ndarray, sample_rate: int, path: Path, audio_format: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if audio_format == "wav":
            sf.write(path, audio, sample_rate, subtype="PCM_16", format="WAV")
            return
        if audio_format != "mp3":
            raise ValueError("Поддерживаются только WAV и MP3")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("Для MP3 не найден ffmpeg; выберите WAV")
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="uni-audio-", suffix=".wav", delete=False) as temp:
                temp_path = temp.name
            sf.write(temp_path, audio, sample_rate, subtype="PCM_16", format="WAV")
            completed = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", temp_path, str(path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0 or not path.is_file():
                raise RuntimeError(completed.stderr.strip() or "ffmpeg не создал MP3")
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    async def synthesize_file(self, text: str, path: str, audio_format: str = "wav") -> ToolResult:
        clean_text = text.strip()
        if not clean_text:
            return ToolResult(success=False, message="Текст аудиопослания пуст")
        output_format = audio_format.casefold().strip()
        output_path = Path(path).resolve()
        if output_path.suffix.casefold() != f".{output_format}":
            return ToolResult(success=False, message="Расширение файла не совпадает с форматом")
        try:
            await self._init_tts()
            audio, sample_rate = await asyncio.to_thread(self._synthesize_audio_safe, clean_text)
            await asyncio.to_thread(
                self._write_audio_file,
                audio,
                sample_rate,
                output_path,
                output_format,
            )
            duration_s = len(audio) / sample_rate
            return ToolResult(
                success=True,
                data={
                    "path": str(output_path),
                    "format": output_format,
                    "duration_seconds": round(duration_s, 2),
                    "sample_rate": sample_rate,
                },
                message=f"Аудиопослание сохранено как {output_format.upper()}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка экспорта аудио: {exc}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "listen":
            text = await self.listen(float(kwargs.get("duration", 4.0)))
            if text:
                return ToolResult(success=True, data=text, message=f"Распознано: {text[:80]}")
            return ToolResult(success=False, message="Речь не распознана")
        if action == "speak":
            text = str(kwargs.get("text", ""))
            success = await self.speak(text)
            return ToolResult(success=success, message="Речь воспроизведена" if success else "Ошибка TTS")
        if action == "synthesize_file":
            return await self.synthesize_file(
                str(kwargs.get("text", "")),
                str(kwargs.get("path", "")),
                str(kwargs.get("format", "wav")),
            )
        return ToolResult(success=False, message=f"Неизвестное действие speech.{action}")
