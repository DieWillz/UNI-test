"""UNI interactive MVP. Run with: py -3.12 -m uni"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel

from uni.agent import Agent
from uni.config import load_config

console = Console()

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="UNI — локальный голосовой помощник")
    parser.add_argument("command", nargs="*", help="Одна команда; без неё запускается непрерывный цикл")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--text", action="store_true", help="Текстовый интерактивный режим вместо микрофона")
    parser.add_argument("--voice", action="store_true", help="Только голосовой ввод")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.text:
        config.agent.input_mode = "text"
    elif args.voice:
        config.agent.input_mode = "voice"
    command = " ".join(args.command).strip() or None

    console.print(
        Panel(
            "[bold cyan]UNI Fast-track MVP[/bold cyan]\n"
            "[dim]Голос • Browser • XToys • Vision • Web search[/dim]",
            border_style="cyan",
        )
    )
    agent = Agent(config)
    try:
        await agent.initialize()
        await agent.run(command)
        return 0
    finally:
        await agent.shutdown()


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]UNI остановлена[/yellow]")


if __name__ == "__main__":
    main()
