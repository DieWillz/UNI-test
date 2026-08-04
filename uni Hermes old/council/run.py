"""CLI for the UNI development council.

Replaces the manual copy-paste loop between AI participants. Delivers a brief
(ideas / files / tasks) to every registered participant through the cheapest
available transport (API when the model is free/local, browser when it is a
closed web chat), collects untrusted replies + signatures, and writes a merged report.

Per MANIFESTO v2.6 §7 the browser adapter is ENABLED by default for FREE web tiers
(so users without money can reach strong models without paying for API). Before any
browser automation the runner informs the user that automation may breach a service
ToS and asks for acknowledgement; it never automates a paid consumer subscription.

Usage:
    python -m uni.council.run --topic "Концепция UNI v2.6" --brief-file brief.md
    python -m uni.council.run --topic "XToys fallback" --brief "Проверь логику..." \
        --file docs/UNI_CONCEPT.md --task "Добавить handoff-протокол" --only DeepSeek QWEN Hermes
    python -m uni.council.run --topic "t" --brief "b" --only Claude ChatGPT --yes-tos
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .participants import load_participants
from .round import CouncilRound

_BROWSER_TOS_NOTICE = (
    "\n[UNI Council · браузерный адаптер]\n"
    "Вы включили опрос участников через веб-интерфейсы ИИ (бесплатные веб-версии).\n"
    "Автоматизация браузера может нарушать условия использования конкретного сервиса;\n"
    "вы берёте на себя ответственность за последствия. Адаптер использует ОТДЕЛЬНЫЙ\n"
    "профиль, не передаёт ваши секреты и не автоматизирует платные подписки (Plus/Advanced).\n"
    "Продолжить? [y/N] "
)


async def _maybe_start_browser(args, cfg) -> tuple[object | None, list]:
    """Start the browser session if browser participants are selected and allowed.

    Returns (browser_session, participants_to_ask). Honours:
    - council.browser_enabled (default True per MANIFESTO v2.6 §7);
    - --no-browser override;
    - free_tier_only: drop any browser participant not marked free_tier.
    """
    participants = load_participants(only=args.only or None)
    browser_participants = [p for p in participants if p.transport == "browser"]

    if not browser_participants:
        return None, participants

    # Drop paid/non-free-tier browser participants if fair use requires free tiers only.
    if cfg.council.free_tier_only:
        paid = [p for p in browser_participants if not p.is_free_tier_browser]
        for p in paid:
            print(f"[skip] Участник {p.name}: не бесплатный веб-уровень — "
                  f"автоматизация платных подписок запрещена (MANIFESTO v2.6 §7).", file=sys.stderr)
        browser_participants = [p for p in browser_participants if p.is_free_tier_browser]
        participants = [p for p in participants if p not in paid]

    if args.no_browser or not cfg.council.browser_enabled:
        print("[info] Браузерный транспорт отключён — участники через браузер пропущены.", file=sys.stderr)
        participants = [p for p in participants if p.transport != "browser"]
        return None, participants

    if not args.yes_tos and cfg.council.inform_tos:
        try:
            answer = input(_BROWSER_TOS_NOTICE)
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer.strip().lower() not in ("y", "yes", "д", "да"):
            print("[info] Согласие не получено — браузерные участники пропущены.", file=sys.stderr)
            participants = [p for p in participants if p.transport != "browser"]
            return None, participants

    try:
        from uni.browser_session import BrowserSession

        browser_session = BrowserSession(
            user_data_dir=cfg.council.browser_profile,  # SEPARATE profile (MANIFESTO v2.6 §7)
            cdp_url=cfg.capabilities.browser.cdp_url,
        )
        await browser_session.start()
    except Exception as exc:
        print(f"[warn] Браузерный транспорт недоступен: {exc}. "
              f"Участники через браузер будут пропущены.", file=sys.stderr)
        participants = [p for p in participants if p.transport != "browser"]
        return None, participants

    # Wire the rate-limit interval into each browser participant's provider.
    for p in browser_participants:
        p.build_provider(
            browser_session=browser_session,
            min_interval_seconds=cfg.council.min_interval_seconds,
        )
    return browser_session, participants


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

    from uni.config import load_config

    cfg = load_config()
    browser_session, participants = await _maybe_start_browser(args, cfg)
    if not participants:
        print("Нет доступных участников для опроса (проверьте транспорт/браузер).", file=sys.stderr)
        return 1

    # Critic + Coordinator are local models when available; else None -> skipped.
    critic = next((p for p in participants if p.name == "Claude" and p.transport == "api"), None)
    coordinator = next((p for p in participants if p.name == "Hermes"), None)

    try:
        round_ = CouncilRound(
            participants=participants,
            browser_session=browser_session,
            artifacts_dir=args.artifacts_dir or cfg.council.artifacts_dir,
            concurrency=args.concurrency or cfg.council.concurrency,
            timeout_seconds=args.timeout or cfg.council.timeout_seconds,
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
    parser.add_argument("--artifacts-dir", default=None, help="Каталог артефактов (по умолч. из config)")
    parser.add_argument("--concurrency", type=int, default=None, help="Параллелизм (по умолч. из config)")
    parser.add_argument("--timeout", type=float, default=None, help="Таймаут на участника, сек (по умолч. из config)")
    parser.add_argument("--no-browser", action="store_true", help="Отключить браузерный транспорт")
    parser.add_argument("--yes-tos", action="store_true", help="Подтвердить ToS-информирование без вопроса")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
