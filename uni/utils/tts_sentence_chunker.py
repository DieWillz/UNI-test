"""uni/utils/tts_sentence_chunker.py — ИНТЕГРИРОВАНО (Директива INT-02, 2026-08-13).

Источник: UNI-reuse-candidates/tts_sentence_chunker.py (выжимка из Hermes
tools/tts_streaming.py). Самостоятельный модуль (только re/time), без зависимостей
Hermes. Положен в канон uni/utils/ для переиспользования в speech.py (флаг
tts.use_chunker). Логика не менялась.
"""

import re
import time
from typing import List, Optional

# Граница предложения: после .!? + пробел/перенос, либо пустая строка.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s|\n)|(?:\n\n)")
# Блоки рассуждения модели — вырезаем, чтобы не озвучивались.
_THINK_BLOCK_RE = re.compile(r"<think[\s>].*?</think>", flags=re.DOTALL)


class SentenceChunker:
    """Инкрементальный резак предложений для LLM-токен-дельт.

    Делит поток текста на предложения так, чтобы каждое озвучивалось
    отдельно. Вырезает <think>-блоки (даже разорванные между дельтами).
    Короткие фрагменты (< min_len) приклеивает к следующему предложению.
    """

    def __init__(self, min_len: int = 20):
        self.min_len = min_len
        self.buf = ""

    def feed(self, delta: str) -> List[str]:
        """Впитать delta; вернуть готовые предложения для озвучки."""
        self.buf = _THINK_BLOCK_RE.sub("", self.buf + delta)
        if "<think" in self.buf and "</think>" not in self.buf:
            return []  # открытый think — тег закроется в следующей дельте
        out: List[str] = []
        start = 0
        while m := SENTENCE_BOUNDARY_RE.search(self.buf, start):
            head = self.buf[: m.end()]
            if len(head.strip()) < self.min_len:
                start = m.end()
                continue
            out.append(head)
            self.buf = self.buf[m.end():]
            start = 0
        return out

    def flush(self) -> List[str]:
        """Слить хвост (конец текста / долгое молчание)."""
        tail = _THINK_BLOCK_RE.sub("", self.buf).strip()
        self.buf = ""
        return [tail] if tail else []


class SpeechInterruptionLatch:
    """Latch прерывания речи.

    Когда пользователь перебивает (говорит/печатает/жмёт PTT), поверхность
    ставит mark(); следующая отправка берёт take() и добавляет помету
    [Note: user interrupted...] к сообщению модели. TTL не даёт старинному
    барджу пометить незапрашиваемое сообщение минуты спустя.
    """

    SPEECH_INTERRUPTED_NOTE = "[Note: the user interrupted your previous spoken reply before it finished.]"
    _TTL_S = 120.0
    _interrupted_at: Optional[float] = None

    @classmethod
    def mark(cls) -> None:
        cls._interrupted_at = time.monotonic()

    @classmethod
    def take(cls) -> bool:
        at, cls._interrupted_at = cls._interrupted_at, None
        return at is not None and time.monotonic() - at < cls._TTL_S


if __name__ == "__main__":
    ch = SentenceChunker()
    parts = []
    for d in ["Привет! Как", " дела? Я", " думаю, погода хорошая.<think>рассуждаю</think> Пока!"]:
        parts += ch.feed(d)
    parts += ch.flush()
    print("Предложения:", parts)
    SpeechInterruptionLatch.mark()
    print("Прервано:", SpeechInterruptionLatch.take())
