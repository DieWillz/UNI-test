"""Тесты интеграции tts_sentence_chunker (Директива INT-02, 2026-08-13).

10 реальных фраз: SentenceChunker режет корректно, вырезает <think>,
склеивает короткие фрагменты. Плюс флаг use_chunker в SpeechConfig
(дефолт True после зелёных тестов) и DEPRECATED-фоллбэк _split_sentences.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.utils.tts_sentence_chunker import SentenceChunker, SpeechInterruptionLatch
from uni.config import SpeechConfig


# 10 реальных фраз (каждая >= 20 символов, чтобы chunker НЕ склеивал)
REAL_PHRASES_TEXT = (
    "Привет, как у тебя прошли выходные? "
    "Я подготовила подробный отчёт по проекту. "
    "Он занял целых три страницы текста. "
    "Основной вывод — план полностью выполнен. "
    "Нужно ли ещё что-то обязательно поправить? "
    "Я могу отправить файл прямо на почту. "
    "Или показать результаты прямо здесь. "
    "Скажи, какой вариант тебе будет удобнее. "
    "Ещё я нашла пару мелких ошибок. "
    "Исправлю их буквально за одну минуту."
)


def test_chunker_10_phrases():
    ch = SentenceChunker(min_len=20)
    # имитируем поток дельт: бьём текст на куски
    parts = []
    step = 17
    for i in range(0, len(REAL_PHRASES_TEXT), step):
        parts += ch.feed(REAL_PHRASES_TEXT[i:i + step])
    parts += ch.flush()
    # 10 самостоятельных предложений (каждое >= min_len 20)
    assert len(parts) == 10, f"ожидали 10 фраз, получили {len(parts)}: {parts}"
    # каждая фраза заканчивается на допустимый знак и не пустая
    for p in parts:
        assert p.strip(), "пустая фраза"
        assert p.strip()[-1] in ".!?"


def test_chunker_short_phrase_merged():
    # фраза < min_len склеивается со следующей (корректное поведение chunker)
    ch = SentenceChunker(min_len=20)
    out = ch.feed("Скажи, как удобнее. Ещё я нашла пару ошибок. ") + ch.flush()
    assert len(out) == 1  # "Скажи, как удобнее." (19 симв) влита в следующую
    assert "Скажи, как удобнее" in out[0] and "ошибок" in out[0]


def test_chunker_strips_think_block():
    ch = SentenceChunker()
    out = ch.feed("Думаю<think>рассуждаю тихо</think> Погода хорошая! Пока.")
    out += ch.flush()
    joined = " ".join(out)
    assert "<think>" not in joined and "рассуждаю" not in joined
    assert "Погода хорошая!" in joined


def test_chunker_short_fragment_merged():
    # короткий фрагмент (< min_len) приклеивается к следующему
    ch = SentenceChunker(min_len=20)
    out = ch.feed("Привет. Я")
    assert out == []  # коротко, ещё не готово
    out += ch.feed(" иду домой. До свидания!")
    out += ch.flush()
    # первое короткое "Привет." склеено со вторым
    assert any("Привет" in s and "иду домой" in s for s in out)


def test_interruption_latch_ttl():
    SpeechInterruptionLatch.mark()
    assert SpeechInterruptionLatch.take() is True
    # второй take -> уже погашено
    assert SpeechInterruptionLatch.take() is False


def test_speechconfig_use_chunker_default_true():
    # INT-02: дефолт True после зелёных тестов
    assert SpeechConfig().use_chunker is True


def test_deprecated_split_sentences_still_works():
    # старый фоллбэк не сломан (не удалён, инвариант 0.2)
    from uni.capabilities.speech import SpeechCapability
    parts = SpeechCapability._split_sentences("Один. Два. Три!")
    assert parts == ["Один.", "Два.", "Три!"]


def test_speechcapability_split_for_tts_uses_chunker():
    # _split_for_tts с use_chunker=True -> через SentenceChunker
    from uni.capabilities.speech import SpeechCapability
    cap = SpeechCapability.__new__(SpeechCapability)
    cap.use_chunker = True
    res = cap._split_for_tts("Первое длинное предложение для проверки. Второе длинное предложение для проверки!")
    assert len(res) == 2
    assert res[0].startswith("Первое") and res[1].startswith("Второе")
    # фоллбэк при use_chunker=False
    cap.use_chunker = False
    res2 = cap._split_for_tts("Первое длинное предложение для проверки. Второе длинное предложение для проверки!")
    assert len(res2) == 2
