"""STT (speech-to-text) capability — аддитивный модуль для десктоп-оверлея.

Опционально использует Whisper (или faster-whisper), если он установлен в
окружении. Если движок недоступен — метод `transcribe` возвращает None, и
server.py отдаёт 501 (Not Implemented), не ломая остальной канон.

Это НЕ трогает существующий speech.py (озвучка). Только дополнение.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

_ENGINE = None
_ENGINE_NAME = "none"


def _load_engine():
    """Лениво загружаем Whisper при первом вызове. Безопасно при отсутствии."""
    global _ENGINE, _ENGINE_NAME
    if _ENGINE is not None or _ENGINE_NAME != "none":
        return _ENGINE
    # 1) пробуем faster-whisper (быстрее, меньше RAM)
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model_size = os.environ.get("UNI_WHISPER_MODEL", "base")
        _ENGINE = WhisperModel(model_size, device="auto", compute_type="int8")
        _ENGINE_NAME = "faster-whisper"
        return _ENGINE
    except Exception:
        pass
    # 2) пробуем openai-whisper
    try:
        import whisper  # type: ignore
        model_size = os.environ.get("UNI_WHISPER_MODEL", "base")
        _ENGINE = whisper.load_model(model_size)
        _ENGINE_NAME = "openai-whisper"
        return _ENGINE
    except Exception:
        pass
    _ENGINE_NAME = "none"
    return None


def engine_name() -> str:
    """Возвращает имя доступного движка или 'none'."""
    _load_engine()
    return _ENGINE_NAME


def transcribe_audio(data: bytes, mime: str = "audio/webm") -> Optional[str]:
    """Принимает сырые байты аудио, возвращает текст или None (если нет движка).

    Поддерживаемые форматы зависят от движка (whisper ест webm/wav/mp3/m4a).
    """
    eng = _load_engine()
    if eng is None:
        return None
    suffix = {  # выбираем расширение по mime для корректного сохранения
        "audio/webm": ".webm", "audio/wav": ".wav", "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a", "audio/ogg": ".ogg",
    }.get(mime, ".webm")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        if _ENGINE_NAME == "faster-whisper":
            segments, _ = eng.transcribe(path)
            return " ".join(seg.text for seg in segments).strip() or None
        else:  # openai-whisper
            result = eng.transcribe(path)
            return (result.get("text") or "").strip() or None
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
