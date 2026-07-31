"""
UNI — голосовой AI-агент. Запуск: python -m uni
"""

import asyncio
import sys
from rich.console import Console
from rich.panel import Panel

from uni.config import load_config
from uni.agent import Agent

console = Console()

def main():
    console.print(Panel("[bold cyan]UNI[/bold cyan]\n[dim]Голосовой помощник для XToys[/dim]", border_style="cyan"))
    
    try:
        config = load_config("config.yaml")
        console.print(f"[green]✅ Конфиг загружен[/green]")
        console.print(f"[dim]Brain: {config.brain.model}[/dim]")
        
        agent = Agent(config)
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️ Остановлено[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
