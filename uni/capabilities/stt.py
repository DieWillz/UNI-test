"""STT (speech-to-text) capability — аддитивный модуль для десктоп-оверлея.

Опционально использует Whisper (или faster-whisper), если он установлен в
окружении. Если движок недоступен — метод `transcribe` возвращает None, и
server.py отдаёт 501 (Not Implemented), не ломая остальной канон.

Это НЕ трогает существующий speech.py (озвучка). Только дополнение.

🤖 FIX (Hermes, 2026-08-12): availability detection (`engine_name`) больше
НЕ инстанцирует модель — это вызывало загрузку/скачивание ~140MB Whisper на
каждом probe (включая JSON `{}` без аудио) и таймаут /api/stt. Теперь
engine_name делает только дешёвую проверку импорта; модель грузится лениво
только при реальном транскрибировании аудио.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

_ENGINE = None
_ENGINE_NAME = "none"
_ENGINE_KIND = None  # "faster-whisper" | "openai-whisper" | None


def _engine_importable() -> Optional[str]:
    """Дешёвая проверка: доступен ли движок (без загрузки модели).

    Возвращает 'faster-whisper', 'openai-whisper' или None. НЕ инстанцирует
    WhisperModel — не тратит сотни МБ и не виснет на сетевой загрузке.
    """
    try:
        import faster_whisper  # type: ignore  # noqa: F401
        return "faster-whisper"
    except Exception:
        pass
    try:
        import whisper  # type: ignore  # noqa: F401
        return "openai-whisper"
    except Exception:
        pass
    return None


def _load_engine():
    """Лениво загружаем Whisper при первом реальном транскрибировании."""
    global _ENGINE, _ENGINE_NAME, _ENGINE_KIND
    if _ENGINE is not None or _ENGINE_KIND is not None:
        return _ENGINE
    kind = _engine_importable()
    if kind is None:
        _ENGINE_NAME = "none"
        return None
    model_size = os.environ.get("UNI_WHISPER_MODEL", "base")
    if kind == "faster-whisper":
        from faster_whisper import WhisperModel  # type: ignore
        _ENGINE = WhisperModel(model_size, device="auto", compute_type="int8")
        _ENGINE_KIND = "faster-whisper"
    else:  # openai-whisper
        import whisper  # type: ignore
        _ENGINE = whisper.load_model(model_size)
        _ENGINE_KIND = "openai-whisper"
    _ENGINE_NAME = _ENGINE_KIND
    return _ENGINE


def engine_name() -> str:
    """Возвращает имя доступного движка или 'none' (без загрузки модели)."""
    kind = _engine_importable()
    return kind if kind is not None else "none"


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
        if _ENGINE_KIND == "faster-whisper":
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
