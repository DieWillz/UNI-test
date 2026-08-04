"""UNI interactive MVP. Run with: py -3.12 -m uni"""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings

# Silero TTS ships a precompiled torch package with a stray `'\^'` escape in its
# source. That emits a harmless SyntaxWarning on import — silence it so UNI's
# startup log stays clean. (Not our code; does not affect functionality.)
warnings.filterwarnings("ignore", category=SyntaxWarning)

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
    parser.add_argument("--autonomous", action="store_true", help="Автономный режим без команд пользователя")
    parser.add_argument("--webui", action="store_true", help="Запустить веб-консоль разработки (UNI Council GUI)")
    args = parser.parse_args()

    if args.webui:
        from uni.webui import run_webui

        run_webui()
        return 0

    config = load_config(args.config)
    if args.text:
        config.agent.input_mode = "text"
    elif args.voice:
        config.agent.input_mode = "voice"
    if args.autonomous:
        config.agent.autonomous.enabled = True
        # движение устройства требует осознанного подтверждения в двух местах;
        # флаг --autonomous явно включает второй (первый — config.capabilities.xtoys.autonomous_physical)
        config.capabilities.xtoys.autonomous_physical = bool(
            config.capabilities.xtoys.autonomous_physical
        )
        config.agent.autonomous.enable_device_motion = True
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
