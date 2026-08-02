"""CLI for the UNI development council.

Replaces the manual copy-paste loop between AI participants. Delivers a brief
(ideas / files / tasks) to every registered participant through the cheapest
available transport (API when the model is free/local, browser when it is a paid
closed web chat), collects untrusted replies + signatures, and writes a merged report.

Usage:
    python -m uni.council.run --topic "Концепция UNI v2.5" --brief-file brief.md
    python -m uni.council.run --topic "XToys fallback" --brief "Проверь логику..." \
        --file docs/UNI_CONCEPT.md --task "Добавить handoff-протокол" --only DeepSeek QWEN Hermes
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .round import CouncilRound
from .participants import load_participants


async def _main(args) -> int:
    brief = args.brief or ""
    if args.brief_file:
        p = Path(args.brief_file)
        if not p.exists():
            print(f"Файл брифа не найден: {p}", file=sys.stderr)
            return 2
        brief = (p.read_text(encoding="utf-8", errors="replace")).strip()

    files: dict[str, str] = {}
    for f in args.file or []:
        fp = Path(f)
        if fp.exists():
            files[fp.name] = fp.read_text(encoding="utf-8", errors="replace")

    # Browser participants need a live browser session. Import lazily so the
    # CLI works for API-only rounds without Playwright installed.
    browser_session = None
    specs = None
    if args.only:
        # When restricting participants we still build from the registry.
        pass
    participants = load_participants(only=args.only or None)
    has_browser = any(p.transport == "browser" for p in participants)
    if has_browser:
        try:
            from uni.browser_session import BrowserSession
            from uni.config import load_config

            cfg = load_config()
            browser_session = BrowserSession(
                user_data_dir=".uni-council-browser-profile",  # SEPARATE profile (MANIFESTO §7)
                cdp_url=cfg.capabilities.browser.cdp_url,
            )
            await browser_session.start()
        except Exception as exc:
            print(f"[warn] Браузерный транспорт недоступен: {exc}. "
                  f"Участники через браузер будут пропущены.", file=sys.stderr)
            participants = [p for p in participants if p.transport != "browser"]

    # Critic + Coordinator are local models when available; else None -> skipped.
    critic = next((p for p in participants if p.name == "Claude" and p.transport == "api"), None)
    coordinator = next((p for p in participants if p.name == "Hermes"), None)

    try:
        round_ = CouncilRound(
            participants=participants,
            browser_session=browser_session,
            artifacts_dir=args.artifacts_dir,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout,
        )
        report = await round_.run(
            topic=args.topic,
            brief=brief,
            files=files,
            tasks=args.task,
            critic=critic,
            coordinator=coordinator,
        )
    finally:
        if browser_session is not None:
            await browser_session.close()

    print("\n" + "=" * 70)
    print(f"Раунд: {report.round_id}  Тема: {report.topic}")
    print(f"Участников опрошено: {len(report.participants)}  "
          f"Ошибок: {len(report.errors)}  Подписей: {len(report.signatures)}")
    print(f"Отчёт: {report.artifacts.get('report', '(нет)')}")
    print("=" * 70)
    if report.synthesis:
        print("\n-- СИНТЕЗ КООРДИНАТОРА --\n")
        print(report.synthesis[:4000])
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="UNI development council runner")
    parser.add_argument("--topic", required=True, help="Тема раунда согласования")
    parser.add_argument("--brief", default="", help="Текст брифа (идеи/задание)")
    parser.add_argument("--brief-file", default="", help="Путь к файлу брифа")
    parser.add_argument("--file", action="append", default=None, help="Файл проекта для передачи участникам")
    parser.add_argument("--task", action="append", default=None, help="Задача для проработки (можно несколько)")
    parser.add_argument("--only", nargs="*", default=None, help="Ограничить участников по именам")
    parser.add_argument("--artifacts-dir", default=".uni-council")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
