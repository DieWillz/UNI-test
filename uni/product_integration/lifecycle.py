from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from uni.contracts import TaskOutcome, TaskStatus
from uni.transports.models import InboundMessage

from .models import LifecycleEvent, LifecycleKind, OutputDelivery, ProductCommand


def _clean_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("command text is required")
    return text


def command_from_text(
    text: str,
    *,
    source: str,
    conversation_id: str = "",
    user_id: str = "",
    message_id: str = "",
    metadata: dict | None = None,
) -> ProductCommand:
    clean_source = str(source or "").strip()
    if not clean_source:
        raise ValueError("command source is required")
    return ProductCommand(
        text=_clean_text(text),
        source=clean_source,
        conversation_id=str(conversation_id or ""),
        user_id=str(user_id or ""),
        message_id=str(message_id or ""),
        metadata=dict(metadata or {}),
    )

def command_from_telegram(message: InboundMessage) -> ProductCommand:
    return command_from_text(
        message.text,
        source=message.transport or "telegram",
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        message_id=message.message_id,
        metadata={
            **dict(message.metadata),
            "reply_to": message.reply_to,
            "attachments": tuple(message.attachments),
        },
    )


def command_from_voice(
    text: str,
    *,
    conversation_id: str = "voice:local",
    user_id: str = "local",
) -> ProductCommand:
    return command_from_text(
        text,
        source="voice",
        conversation_id=conversation_id,
        user_id=user_id,
    )


def acknowledgement_event(command: ProductCommand) -> LifecycleEvent:
    return LifecycleEvent(
        command_id=command.command_id,
        kind=LifecycleKind.ACKNOWLEDGED,
        text="Поняла. Команда принята, формирую план.",
        terminal=False,
    )

def plan_event(command: ProductCommand, steps: Iterable[str]) -> LifecycleEvent:
    normalized = [str(step).strip() for step in steps if str(step).strip()]
    if not normalized:
        raise ValueError("plan steps are required")
    return LifecycleEvent(
        command_id=command.command_id,
        kind=LifecycleKind.PLAN_AVAILABLE,
        text=f"План: {len(normalized)} этапа.",
        terminal=False,
        metadata={"steps": normalized},
    )


def final_event(command: ProductCommand, outcome: TaskOutcome) -> LifecycleEvent:
    task_status = outcome.status.value
    verification_status = outcome.verification.status.value
    metadata = {
        "task_id": outcome.task_id,
        "task_status": task_status,
        "verification_status": verification_status,
        "evidence_count": len(outcome.verification.evidence),
    }
    if outcome.status is TaskStatus.VERIFIED:
        message = outcome.message.strip() or "Результат независимо подтверждён."
        return LifecycleEvent(
            command_id=command.command_id,
            kind=LifecycleKind.VERIFIED,
            text=f"VERIFIED: {message}",
            terminal=True,
            metadata=metadata,
        )
    reason = outcome.verification.reason.strip() or "independent verification missing"
    return LifecycleEvent(
        command_id=command.command_id,
        kind=LifecycleKind.NOT_VERIFIED,
        text=f"NOT_VERIFIED: {reason}",
        terminal=True,
        metadata=metadata,
    )

async def deliver_tts(
    event: LifecycleEvent,
    speaker: Callable[[str], Awaitable[bool]],
) -> OutputDelivery:
    try:
        delivered = bool(await speaker(event.text))
        return OutputDelivery(
            channel="tts",
            delivered=delivered,
            error="" if delivered else "tts returned false",
        )
    except Exception as exc:
        return OutputDelivery(channel="tts", delivered=False, error=str(exc))
