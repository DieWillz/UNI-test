"""
uni.__main__ — точка входа для `python -m uni`.

Запуск:
    python -m uni [путь_к_config.yaml]

По умолчанию читает ./config.yaml.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel

from uni.config import load_config

console = Console()

BANNER = (
    "[bold cyan]UNI[/bold cyan]\n"
    "[dim]Локальный автономный AI-агент — MVP 0.1[/dim]"
)


def main() -> None:
    console.print(Panel.fit(BANNER, border_style="cyan"))

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[bold red]✗ Ошибка конфигурации:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — CLI top-level, показываем пользователю
        console.print(f"[bold red]✗ Некорректный config.yaml:[/bold red] {e}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Config загружен из [bold]{config_path}[/bold]")
    console.print(f"  Brain: [yellow]{cfg.brain.model}[/yellow] @ {cfg.brain.base_url}")
    console.print(f"  Role по умолчанию: [yellow]{cfg.agent.default_role}[/yellow]")
    console.print(
        f"  Capabilities сконфигурированы: "
        f"[yellow]{', '.join(cfg.capabilities.keys())}[/yellow]"
    )
    console.print(
        "\n[dim]Event loop ещё не подключён — ждёт Build 10 (DeepSeek).[/dim]"
    )


if __name__ == "__main__":
    main()
