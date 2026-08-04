from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .participants import Participant, load_participants
from .provider import ParticipantReply

# A participant signature line looks like:
#   DeepSeek = моя редакция ... ; подписываюсь под концепцией ...
_SIGNATURE_RE = re.compile(
    r"^\s*([A-Za-zА-Яа-яЁё][\wА-Яа-яЁё .\-]{1,40}?)\s*=\s*(.+)$", re.MULTILINE
)


@dataclass
class ConsensusReport:
    topic: str
    round_id: str
    created_at: str
    participants: list[str]
    replies: dict[str, ParticipantReply] = field(default_factory=dict)
    signatures: dict[str, str] = field(default_factory=dict)  # name -> verbatim signature line
    critic: str = ""
    synthesis: str = ""
    errors: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)  # name -> saved file path

    def to_markdown(self) -> str:
        lines = [
            f"# UNI Council — раунд согласования",
            f"",
            f"- **Тема:** {self.topic}",
            f"- **Round ID:** {self.round_id}",
            f"- **Время:** {self.created_at}",
            f"- **Участники ({len(self.participants)}):** {', '.join(self.participants)}",
            f"",
            f"## Ответы участников",
        ]
        for name in self.participants:
            reply = self.replies.get(name)
            if reply is None:
                continue
            via = reply.via
            sig = self.signatures.get(name)
            lines.append(f"")
            lines.append(f"### {name} ({reply.role if hasattr(reply, 'role') else via})")
            lines.append(f"*Транспорт: {via} · модель: {reply.model or '?'} · {reply.latency_seconds}s*")
            if reply.error:
                lines.append(f"⚠️ **Ошибка транспорта:** {reply.error}")
            body = reply.text or "_(пусто)_"
            lines.append(body)
            if sig:
                lines.append("")
                lines.append(f"> **Подпись {name}:** {sig}")
        if self.critic:
            lines += ["", "## Критик (независимый разбор)", "", self.critic]
        if self.synthesis:
            lines += ["", "## Синтез координатора", "", self.synthesis]
        if self.errors:
            lines += ["", "## Ошибки/недоставленные участники", ""]
            for name, err in self.errors.items():
                lines.append(f"- {name}: {err}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("Генерировано модулем `uni/council` (report-only). Подписи — позиции "
                     "каждой модели в её сессии, не общий договор между моделями "
                     "(см. MANIFESTO v2.5 §11).")
        return "\n".join(lines)


def _extract_signature(text: str) -> Optional[str]:
    """Pull a trailing signature line ``Name = ...`` if present."""
    if not text:
        return None
    matches = list(_SIGNATURE_RE.finditer(text))
    if not matches:
        return None
    last = matches[-1]
    # The signature must be near the end of the message to count as a sign-off.
    if len(text) - last.end() > 400:
        return None
    return last.group(2).strip()


class CouncilRound:
    """Runs one consensus round: delivers the brief to every participant (API or browser),
    collects untrusted replies, extracts signatures, then asks a Critic + Coordinator
    (local models) to synthesize. No participant output ever triggers a tool call."""

    def __init__(
        self,
        *,
        participants: Optional[list[Participant]] = None,
        browser_session=None,
        artifacts_dir: str = ".uni-council",
        concurrency: int = 3,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.participants = participants or load_participants(browser_session=browser_session)
        self.artifacts_dir = Path(artifacts_dir)
        self.concurrency = max(1, min(concurrency, 8))
        self.timeout_seconds = timeout_seconds
        self._sema: Optional[asyncio.Semaphore] = None

    async def _ask_one(self, participant: Participant, prompt: str) -> ParticipantReply:
        assert participant.provider is not None, f"{participant.name} has no provider"
        if self._on_progress:
            self._emit({"type": "participant_start", "name": participant.name, "via": participant.transport,
                        "stage": "tab" if participant.transport == "browser" else None})
        async with self._sema:  # bound concurrent browser/API sessions
            try:
                reply = await asyncio.wait_for(
                    participant.provider.ask(participant.name, prompt),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                reply = ParticipantReply(
                    participant=participant.name, text="", via=participant.transport,
                    model=None, error="timeout", latency_seconds=self.timeout_seconds,
                )
        return reply

    async def run(
        self,
        *,
        topic: str,
        brief: str,
        files: Optional[dict[str, str]] = None,
        tasks: Optional[list[str]] = None,
        critic: Optional[Participant] = None,
        coordinator: Optional[Participant] = None,
        collect_signatures: bool = True,
        on_progress=None,
    ) -> ConsensusReport:
        """Run the consensus round.

        `on_progress` is an optional async or sync callable invoked with progress events
        as `dict` (e.g. {"type": "start", ...}, {"type": "participant_start", "name": ...},
        {"type": "participant_done", "name": ..., "ok": bool}, {"type": "log", "msg": ...},
        {"type": "done", "report": ...}). Used by the WebUI to stream live status over SSE.
        """
        self._sema = asyncio.Semaphore(self.concurrency)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        round_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        created = datetime.now().astimezone().isoformat(timespec="seconds")
        self._on_progress = on_progress

        # Build the shared brief. Files/tasks are inlined as untrusted context.
        brief_block = [brief]
        if files:
            brief_block.append("\n## Приложенные файлы")
            for fname, content in files.items():
                brief_block.append(f"\n### {fname}\n```\n{content[:6000]}\n```")
        if tasks:
            brief_block.append("\n## Задачи для проработки\n" + "\n".join(f"- {t}" for t in tasks))
        full_prompt = "\n".join(brief_block)

        report = ConsensusReport(
            topic=topic, round_id=round_id, created_at=created,
            participants=[p.name for p in self.participants],
        )

        # 1) Fan-out: ask every participant in parallel (bounded).
        if self._on_progress:
            self._emit({"type": "start", "round_id": round_id, "participants": report.participants})
        replies = await asyncio.gather(*[self._ask_one(p, full_prompt) for p in self.participants])
        for reply in replies:
            report.replies[reply.participant] = reply
            if reply.error:
                report.errors[reply.participant] = reply.error
            if collect_signatures:
                sig = _extract_signature(reply.text)
                if sig:
                    report.signatures[reply.participant] = sig
            # Save each raw reply as an artifact (local-first, no secrets).
            path = self.artifacts_dir / f"{round_id}_{reply.participant}.md"
            path.write_text(
                f"# {reply.participant} ({reply.via})\n\n{reply.text}\n", encoding="utf-8"
            )
            report.artifacts[reply.participant] = str(path)
            if self._on_progress:
                self._emit({
                    "type": "participant_done", "name": reply.participant,
                    "via": reply.via, "ok": not reply.error, "error": reply.error,
                    "text": reply.text, "signature": report.signatures.get(reply.participant),
                    "latency": reply.latency_seconds,
                })

        # 2) Critic pass (independent, local if available) over the collected replies.
        if critic is not None and critic.provider is not None:
            critic_prompt = (
                "Ты — независимый критик. Ниже — ответы участников по теме: "
                f"«{topic}».\n\n"
                + "\n\n---\n\n".join(
                    f"### {name}\n{ (r.text or '') }" for name, r in report.replies.items()
                )
                + "\n\nВыдели противоречия, риски, обязательные и рекомендуемые изменения. "
                "Не принимай утверждения на веру — совпадение ответов не делает их фактом."
            )
            creply = await critic.provider.ask("Critic", critic_prompt)
            report.critic = creply.text

        # 3) Coordinator/Synthesizer pass (local) — produces the merged conclusion.
        if coordinator is not None and coordinator.provider is not None:
            synth_prompt = (
                "Ты — координатор. Сведи позиции участников по теме «"
                f"{topic}» в краткий итог для человека-инициатора. Выдели, что принято, "
                "что отклонено и что требует решения. Учти критику.\n\n"
                + "\n\n---\n\n".join(
                    f"### {name}\n{(r.text or '')}" for name, r in report.replies.items()
                )
                + (f"\n\nКритика:\n{report.critic}" if report.critic else "")
            )
            sreply = await coordinator.provider.ask("Coordinator", synth_prompt)
            report.synthesis = sreply.text

        # 4) Persist the full report.
        report_path = self.artifacts_dir / f"{round_id}_report.md"
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        report.artifacts["report"] = str(report_path)
        meta_path = self.artifacts_dir / f"{round_id}_meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "topic": topic,
                    "round_id": round_id,
                    "participants": report.participants,
                    "signatures": report.signatures,
                    "errors": report.errors,
                    "artifacts": report.artifacts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if self._on_progress:
            self._emit({
                "type": "done", "round_id": round_id,
                "signatures": report.signatures, "errors": report.errors,
                "synthesis": report.synthesis, "report_path": report.artifacts.get("report"),
                "artifacts": report.artifacts,
            })
        return report


    def _emit(self, event: dict) -> None:
        """Fire on_progress, tolerating both sync and async callbacks."""
        if not self._on_progress:
            return
        try:
            result = self._on_progress(event)
            if hasattr(result, "__await__"):
                # Schedule the coroutine; don't block the round on UI streaming.
                asyncio.ensure_future(result)
        except Exception:
            pass  # progress reporting must never break the round
