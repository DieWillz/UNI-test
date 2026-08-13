"""
voice_silence_detect.py — АДАПТИРОВАННАЯ ВЫЖИМКА из Hermes tools/voice_mode.py
для проекта Юни (C:\\LLM\\UNI\\uni).

Источник: hermes-agent/tools/voice_mode.py (2308 строк, © Hermes Agent).
Взято ТОЛЬКО полезное для Юни, очищено от зависимостей Hermes
(hermes_constants, hermes_cli.config, sys.prefix/venv-хинты и т.д.).

ЧТО ПЕРЕНЕСЕНО (паттерны):
- Lazy-import звука (sounddevice/numpy) — модуль не падает в headless.
- Silence-detection: автостоп записи после N секунд тишины (RMS-порог).
- Запись в WAV (stdlib wave), 16kHz mono int16 (Whisper-friendly).

Юни уже имеет микрофон в uni/desktop/renderer/app.js (MediaRecorder->/api/stt)
и uni/capabilities/speech.py. Этот модуль — АЛЬТЕРНАТИВНЫЙ/дополнительный
push-to-talk для desktop на базе sounddevice (как у Hermes), с silence-detection.

Лицензия: код Hermes — см. AGENTS.md hermes-agent. Выжимка предоставлена
для анализа другими ИИ (пользователь запросил сложить полезное отдельно).
"""

import logging
import math
import os
import platform
import wave
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)

# --- Параметры записи (Whisper-friendly) ---
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SAMPLE_WIDTH = 2

# --- Silence-detection ---
SILENCE_RMS_THRESHOLD = 200   # RMS ниже этого = тишина (int16: 0..32767)
SILENCE_DURATION_SECONDS = 3.0


def _import_audio():
    """Lazy-import sounddevice + numpy. Падает ImportError/OSError, если нет PortAudio."""
    import sounddevice as sd
    import numpy as np
    return sd, np


def audio_available() -> bool:
    try:
        _import_audio()
        return True
    except (ImportError, OSError):
        return False


def _default_input_samplerate(sd) -> int:
    try:
        info = sd.query_devices(None, "input")
        rate = info.get("default_samplerate") if isinstance(info, dict) else getattr(info, "default_samplerate", None)
        if isinstance(rate, (int, float)) and rate > 0:
            return int(round(rate))
    except Exception:
        pass
    return SAMPLE_RATE


def _rms(int16_samples) -> float:
    """Среднеквадратичное отклонение int16-буфера (np.array)."""
    if int16_samples.size == 0:
        return 0.0
    return float(math.sqrt((int16_samples.astype("int64") ** 2).mean()))


def record_until_silence(max_seconds: float = 20.0, on_level=None) -> str | None:
    """
    Запись с микрофона до N секунд тишины. Возвращает путь к WAV или None.

    on_level(rms, is_silence) — опциональный callback для UI-индикатора.

    Адаптировано из voice_mode.py (_record_voice / silence loop).
    """
    try:
        sd, np = _import_audio()
    except (ImportError, OSError) as e:
        logger.warning("audio libraries unavailable: %s", e)
        return None

    sd.default.samplerate = _default_input_samplerate(sd)
    blocksize = int(SAMPLE_RATE * 0.1)  # 100 ms
    silence_frames = 0
    silence_limit = int(SILENCE_DURATION_SECONDS * (SAMPLE_RATE / blocksize))
    max_frames = int(max_seconds * (SAMPLE_RATE / blocksize))
    frames = []

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=blocksize,
            dtype="int16", channels=CHANNELS,
        ) as stream:
            for i in range(max_frames):
                data, _ = stream.read(blocksize)
                arr = np.frombuffer(data, dtype="int16")
                frames.append(data)
                rms = _rms(arr)
                is_sil = rms < SILENCE_RMS_THRESHOLD
                if on_level:
                    try:
                        on_level(rms, is_sil)
                    except Exception:
                        pass
                silence_frames = 0 if not is_sil else silence_frames + 1
                if silence_frames >= silence_limit and len(frames) > silence_limit:
                    break
    except Exception as e:
        logger.warning("record failed: %s", e)
        return None

    if not frames:
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = tmp.name
    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return path
    except Exception as e:
        logger.warning("wav write failed: %s", e)
        try:
            os.unlink(path)
        except OSError:
            pass
        return None


if __name__ == "__main__":
    if not audio_available():
        print("sounddevice/numpy не установлены (pip install sounddevice numpy)")
    else:
        print("Запись до тишины (3с)… говорите в микрофон")
        out = record_until_silence()
        print("WAV:", out)
