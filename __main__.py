"""
UNI — локальный автономный AI-агент. MVP 0.1.

Запуск:
    python -m uni [команда] [-c|--config путь_к_config.yaml]

Примеры:
    python -m uni "Открой YouTube"
    python -m uni -c my_config.yaml "Найди видео про LM Studio"
    python -m uni  (интерактивный режим)
"""

import argparse
import asyncio
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

BANNER = (
    "[bold cyan]UNI[/bold cyan]\n"
    "[dim]Локальный автономный AI-агент — MVP 0.1[/dim]"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UNI AI Agent — Локальный автономный AI-агент",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Примеры:\n  python -m uni \"Открой YouTube\"\n  python -m uni -c my_config.yaml \"Найди видео про LM Studio\"\n  python -m uni  (интерактивный режим)"
    )
    parser.add_argument("command", nargs="?", default=None, help="Команда для агента")
    parser.add_argument("-c", "--config", default=None, help="Путь к config.yaml (по умолчанию: config.yaml в корне проекта)")
    
    args = parser.parse_args()
    
    # Определяем путь к конфигу
    config_path = args.config if args.config else "config.yaml"
    
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[bold red]❌ Ошибка:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]❌ Ошибка загрузки конфига:[/bold red] {e}")
        sys.exit(1)

    console.print(Panel.fit(BANNER, border_style="cyan"))
    console.print(f"   Brain: {config.brain.base_url} / {config.brain.model}")
    console.print(f"   Config: [dim]{Path(config_path).resolve()}[/dim]")

    agent = Agent(config)
    
    try:
        if args.command:
            console.print(f"   Выполнение команды: [cyan]\"{args.command}\"[/cyan]")
            asyncio.run(agent.run_cycle(user_input=args.command))
        else:
            console.print("   Режим: [yellow]Интерактивный (ожидание голосовой команды)[/yellow]")
            asyncio.run(agent.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]⏸️ Агент остановлен пользователем[/yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Критическая ошибка:[/bold red] {e}")
        sys.exit(1)
    finally:
        pass


if __name__ == "__main__":
    main()