from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uni.contracts import Evidence, TaskOutcome, TaskStatus, Verification, VerificationStatus
from uni.product_integration import (
    LifecycleKind,
    acknowledgement_event,
    command_from_telegram,
    command_from_text,
    command_from_voice,
    deliver_tts,
    final_event,
    plan_event,
)
from uni.transports.models import InboundMessage


def _verified_outcome(command: str = "save file") -> TaskOutcome:
    return TaskOutcome(
        command=command,
        status=TaskStatus.VERIFIED,
        message="Файл сохранён.",
        verification=Verification(
            status=VerificationStatus.VERIFIED,
            method="filesystem.readback",
            reason="fresh observation",
            evidence=[Evidence(source="filesystem", summary="file exists")],
        ),
    )

def test_all_ingress_paths_normalize_to_one_command_shape() -> None:
    web = command_from_text(
        "открой сайт", source="webui", conversation_id="web:1", user_id="owner"
    )
    voice = command_from_voice(
        "открой сайт", conversation_id="voice:local", user_id="owner"
    )
    telegram = command_from_telegram(
        InboundMessage(
            transport="telegram",
            message_id="42",
            conversation_id="tg:1",
            user_id="owner",
            text="открой сайт",
            timestamp=datetime.now(timezone.utc),
        )
    )

    assert {web.text, voice.text, telegram.text} == {"открой сайт"}
    assert web.source == "webui"
    assert voice.source == "voice"
    assert telegram.source == "telegram"
    assert telegram.message_id == "42"


def test_acknowledgement_is_receipt_not_completion() -> None:
    command = command_from_text("сохрани файл", source="cli")
    event = acknowledgement_event(command)
    assert event.kind is LifecycleKind.ACKNOWLEDGED
    assert event.terminal is False
    assert "verified" not in event.metadata
    assert "готов" not in event.text.casefold()

def test_plan_event_requires_real_steps() -> None:
    command = command_from_text("multi step", source="webui")
    with pytest.raises(ValueError, match="steps"):
        plan_event(command, [])

    event = plan_event(command, ["Открыть приложение", "Сохранить файл"])
    assert event.kind is LifecycleKind.PLAN_AVAILABLE
    assert event.metadata["steps"] == ["Открыть приложение", "Сохранить файл"]


def test_final_event_uses_canonical_task_outcome() -> None:
    command = command_from_text("save file", source="webui")
    verified = final_event(command, _verified_outcome())
    assert verified.kind is LifecycleKind.VERIFIED
    assert verified.terminal is True
    assert verified.metadata["task_status"] == "verified"

    not_verified = final_event(
        command,
        TaskOutcome.finalize(
            command="save file",
            message="готово",
            verification=Verification(reason="fresh observation unavailable"),
        ),
    )
    assert not_verified.kind is LifecycleKind.NOT_VERIFIED
    assert not_verified.metadata["task_status"] == "not_verified"
    assert "готово" not in not_verified.text.casefold()
    assert "not_verified" in not_verified.text.casefold()

@pytest.mark.asyncio
async def test_tts_failure_does_not_change_execution_outcome() -> None:
    command = command_from_text("save file", source="voice")
    event = final_event(command, _verified_outcome())

    async def broken_speaker(text: str) -> bool:
        raise RuntimeError("speaker unavailable")

    delivery = await deliver_tts(event, broken_speaker)
    assert delivery.delivered is False
    assert "speaker unavailable" in delivery.error
    assert event.kind is LifecycleKind.VERIFIED


@pytest.mark.asyncio
async def test_tts_never_speaks_success_for_not_verified() -> None:
    command = command_from_text("save file", source="voice")
    event = final_event(
        command,
        TaskOutcome.finalize(
            command="save file",
            message="готово",
            verification=Verification(reason="verification missing"),
        ),
    )
    spoken: list[str] = []

    async def speaker(text: str) -> bool:
        spoken.append(text)
        return True

    delivery = await deliver_tts(event, speaker)
    assert delivery.delivered is True
    assert spoken and "not_verified" in spoken[0].casefold()
    assert "готово" not in spoken[0].casefold()