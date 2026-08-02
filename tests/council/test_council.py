from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from uni.council.participants import Participant, load_participants
from uni.council.provider import (
    ApiProvider,
    BrowserProvider,
    CouncilProvider,
    ParticipantReply,
    build_provider,
)
from uni.council.round import CouncilRound, _extract_signature


class _FakeProvider(CouncilProvider):
    scheme = "fake"

    def __init__(self, reply_text: str, error: str | None = None, via: str = "api"):
        self._text = reply_text
        self._error = error
        self._via = via
        self.calls = 0

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000):
        self.calls += 1
        return ParticipantReply(
            participant=participant,
            text=self._text,
            via=self._via,
            model="fake-model",
            error=self._error,
        )


def _make_participants(with_signatures: bool = True):
    base = "Согласен с концепцией. Нужно добавить Handoff-протокол.\n"
    sig = "DeepSeek = моя редакция; подписываюсь под концепцией."
    p1 = Participant("DeepSeek", "architect", "api", {})
    p1.provider = _FakeProvider(base + (sig if with_signatures else ""))
    p2 = Participant("QWEN", "editor", "api", {})
    p2.provider = _FakeProvider("Принимаю. " + (sig.replace("DeepSeek", "QWEN") if with_signatures else ""))
    p3 = Participant("Claude", "critic", "browser", {})
    p3.provider = _FakeProvider("Отвергаю скрытую манипуляцию. " + (sig.replace("DeepSeek", "Claude") if with_signatures else ""), via="browser")
    return [p1, p2, p3]


def test_extract_signature_returns_none_when_absent():
    assert _extract_signature("Просто текст без подписи.") is None


def test_extract_signature_pulls_trailing_line():
    text = "Тело ответа.\n\nDeepSeek = моя редакция; подписываюсь."
    assert _extract_signature(text) == "моя редакция; подписываюсь."


def test_extract_signature_ignores_early_signature():
    # Signature far from the end must NOT be treated as sign-off.
    text = ("DeepSeek = ранняя подпись.\n" * 5) + "Основной длинный текст " + "x" * 500
    assert _extract_signature(text) is None


def test_build_provider_api_uses_openai_client():
    prov = build_provider({"transport": "api", "base_url": "http://x/v1", "api_key": "k", "model": "m"})
    assert isinstance(prov, ApiProvider)
    assert prov.model == "m"


def test_load_participants_redacts_api_key():
    specs = [{"name": "X", "transport": "api", "base_url": "u", "api_key": "SECRET", "model": "m"}]
    parts = load_participants(specs)
    assert parts[0].spec.get("api_key") is None
    assert parts[0].spec.get("_has_api_key") is True


def test_load_participants_filter_by_name():
    parts = load_participants(only=["DeepSeek", "QWEN"])
    names = {p.name for p in parts}
    assert names == {"DeepSeek", "QWEN"}


def test_round_collects_replies_signatures_and_artifacts(tmp_path):
    participants = _make_participants()
    round_ = CouncilRound(participants=participants, artifacts_dir=str(tmp_path), concurrency=3)

    async def go():
        return await round_.run(
            topic="Тест концепции",
            brief="Проверьте идею.",
            critic=participants[2],
            coordinator=participants[0],
        )

    report = asyncio.run(go())
    # All three were asked.
    assert set(report.participants) == {"DeepSeek", "QWEN", "Claude"}
    assert len(report.replies) == 3
    # Signatures extracted from all three.
    assert set(report.signatures) == {"DeepSeek", "QWEN", "Claude"}
    assert "подписываюсь" in report.signatures["DeepSeek"]
    # Critic + coordinator passes produced text.
    assert report.critic
    assert report.synthesis
    # Artifacts persisted locally.
    assert (tmp_path / f"{report.round_id}_report.md").exists()
    # Browser transport recorded correctly.
    assert report.replies["Claude"].via == "browser"


def test_round_isolated_participant_failure_is_non_fatal(tmp_path):
    ok = Participant("Ok", "x", "api", {})
    ok.provider = _FakeProvider("Нормальный ответ.")
    bad = Participant("Bad", "x", "api", {})
    bad.provider = _FakeProvider("", error="connection reset")
    round_ = CouncilRound(participants=[ok, bad], artifacts_dir=str(tmp_path))

    async def go():
        return await round_.run(topic="t", brief="b")

    report = asyncio.run(go())
    assert report.replies["Ok"].text == "Нормальный ответ."
    assert report.errors.get("Bad") == "connection reset"
    # Round still completed and produced a report.
    assert (tmp_path / f"{report.round_id}_report.md").exists()


def test_browser_provider_requires_session():
    spec = {"transport": "browser", "host": "chatgpt.com"}
    with pytest.raises(ValueError):
        build_provider(spec)  # no browser_session -> cannot build
