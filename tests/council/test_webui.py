from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uni.council.participants import Participant
from uni.council.provider import CodexProvider
from uni.council.provider import BrowserProvider, CouncilProvider, ParticipantReply, build_provider
from uni.council.round import CouncilRound
from uni.webui import server


def test_frontend_has_no_binary_nul_or_trailing_content() -> None:
    content = server._FRONTEND.read_bytes()
    assert b"\x00" not in content
    assert content.decode("utf-8").rstrip().endswith("</html>")


def test_grok_uses_current_browser_host() -> None:
    from uni.council.participants import DEFAULT_PARTICIPANTS

    grok = next(item for item in DEFAULT_PARTICIPANTS if item["name"] == "Grok")
    assert grok["host"] == "grok.com"


def test_qwen_studio_and_coder_have_distinct_hosts() -> None:
    from uni.council.participants import DEFAULT_PARTICIPANTS

    hosts = {
        item["name"]: item["host"]
        for item in DEFAULT_PARTICIPANTS
        if item["name"] in {"QWEN", "Qwen Coder"}
    }
    assert hosts == {"QWEN": "chat.qwen.ai", "Qwen Coder": "coder.qwen.ai"}


def test_frontend_roll_call_has_no_removed_notice_dependency() -> None:
    source = server._FRONTEND.read_text(encoding="utf-8")
    assert 'id="tosAck"' not in source
    assert "tos_acknowledged" not in source
    # v2.6 (restored via index-old.html) uses runRollCall; the wiring must exist on
    # the live frontend without depending on a removed ToS notice.
    assert "runRollCall" in source


def test_browser_participant_status_uses_open_cdp_tab(monkeypatch) -> None:
    monkeypatch.setattr(server, "_open_browser_hosts", lambda _url: {"chat.deepseek.com"})
    cfg = SimpleNamespace(
        council=SimpleNamespace(
            browser_enabled=True,
            min_interval_seconds=1,
            api_endpoints={},
        ),
        capabilities=SimpleNamespace(browser=SimpleNamespace(cdp_url="http://127.0.0.1:9222")),
    )

    statuses = server._participant_statuses(cfg)
    by_name = {item["name"]: item for item in statuses}

    assert by_name["DeepSeek"]["status"] == "ready"
    assert by_name["Claude"]["status"] == "configured"


def test_validated_files_preserves_text() -> None:
    files = server._validated_files({"concept.txt": "UNI concept", "notes.md": "# Notes"})
    assert files == {"concept.txt": "UNI concept", "notes.md": "# Notes"}


def test_validated_files_rejects_traversal_duplicates_and_oversize() -> None:
    assert server._validated_files({"../concept.txt": "safe name"}) == {"concept.txt": "safe name"}
    with pytest.raises(ValueError, match="exceeds"):
        server._validated_files({"large.txt": "x" * (server._MAX_FILE_CHARS + 1)})
    with pytest.raises(ValueError, match="at most"):
        server._validated_files({f"{index}.txt": "x" for index in range(server._MAX_FILES + 1)})


def test_history_reads_only_bounded_meta_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "_ROOT", tmp_path)
    artifacts = tmp_path / ".uni-council"
    artifacts.mkdir()
    (artifacts / "round-1_meta.json").write_text(
        json.dumps(
            {
                "round_id": "round-1",
                "topic": "Test",
                "participants": ["Codex"],
                "signatures": {"Codex": "yes"},
                "errors": {},
                "artifacts": {"report": ".uni-council/round-1_report.md"},
            }
        ),
        encoding="utf-8",
    )
    history = server._history(".uni-council")
    assert history[0]["round_id"] == "round-1"
    assert history[0]["signatures"] == 1


def test_browser_session_uses_active_async_loop(monkeypatch) -> None:
    events: list[str] = []

    class FakeSession:
        def __init__(self, **kwargs):
            events.append("init")

        async def start(self):
            asyncio.get_running_loop()
            events.append("start")

    monkeypatch.setattr("uni.browser_session.BrowserSession", FakeSession)
    participant = Participant(
        "BrowserAI",
        "reviewer",
        "browser",
        {"free_tier": True, "host": "example.test"},
    )
    built: list[object] = []
    monkeypatch.setattr(participant, "build_provider", lambda **kwargs: built.append(kwargs["browser_session"]))
    cfg = SimpleNamespace(
        council=SimpleNamespace(free_tier_only=True, browser_enabled=True, browser_profile=".profile", min_interval_seconds=1),
        capabilities=SimpleNamespace(browser=SimpleNamespace(cdp_url=None)),
    )

    session, selected = asyncio.run(server._maybe_start_browser(cfg, [participant]))

    assert events == ["init", "start"]
    assert selected == [participant]
    assert built == [session]


def test_codex_provider_parses_current_jsonl_schema(monkeypatch) -> None:
    line = json.dumps(
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Codex answer"}}
    ).encode()

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return line + b"\n", b""

    async def fake_create(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    reply = asyncio.run(CodexProvider(command="codex").ask("Codex", "Review"))
    assert reply.error is None
    assert reply.text == "Codex answer"


def test_browser_provider_factory_uses_constructor_defaults() -> None:
    session = object()
    provider = build_provider(
        {"transport": "browser", "host": "chat.deepseek.com", "browser_session": session}
    )
    assert isinstance(provider, BrowserProvider)
    assert provider.prompt_selector == BrowserProvider.DEFAULT_PROMPT_SELECTOR
    assert provider.answer_selector == BrowserProvider.DEFAULT_ANSWER_SELECTOR


def test_round_does_not_append_signature_instructions(tmp_path: Path) -> None:
    class CaptureProvider(CouncilProvider):
        def __init__(self):
            self.prompt = ""

        async def ask(self, participant, prompt, *, max_tokens=2000):
            self.prompt = prompt
            return ParticipantReply(participant, "ok", "api", "fake")

    provider = CaptureProvider()
    participant = Participant("DeepSeek", "test", "api", {}, provider)
    asyncio.run(
        CouncilRound(participants=[participant], artifacts_dir=str(tmp_path)).run(
            topic="test", brief="Answer with one short line"
        )
    )
    assert provider.prompt == "Answer with one short line"


def test_browser_send_requires_cleared_composer() -> None:
    class Box:
        value = "message"

        async def press(self, key):
            assert key == "Enter"
            self.value = ""

        async def evaluate(self, script):
            return not self.value.strip()

    class Page:
        async def wait_for_timeout(self, milliseconds):
            return None

    provider = BrowserProvider(browser_session=object(), host="example.test")
    asyncio.run(provider._send_and_verify(Page(), Box()))
