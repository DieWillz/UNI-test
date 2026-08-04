import asyncio
from typing import Optional
from rich.console import Console
from uni.brain import Brain
from uni.config import Config
from uni.state import AgentState
from uni.working_memory import WorkingMemory
from uni.capabilities.registry import CapabilityRegistry
from uni.tools import ToolExecutor, get_tool_schemas

console = Console()

class EventLoop:
    def __init__(self, brain: Brain, capabilities: CapabilityRegistry, memory: WorkingMemory,
                 tool_executor: ToolExecutor, config: Config):
        self.brain = brain
        self.capabilities = capabilities
        self.memory = memory
        self.tool_executor = tool_executor
        self.config = config
        self.state = AgentState.IDLE
        self._running = False

    async def run_cycle(self, user_input: Optional[str] = None):
        console.print("\n[bold cyan]🔄 Цикл[/bold cyan]")
        self.state = AgentState.LISTENING

        if not user_input:
            speech = self.capabilities.get("speech")
            if speech:
                console.print("[dim]🎤 Слушаю... (5 сек)[/dim]")
                try:
                    user_input = await speech.listen(duration=5)
                    if user_input:
                        console.print(f"[yellow]🎤 Распознано: {user_input}[/yellow]")
                except Exception as e:
                    console.print(f"[red]❌ STT ошибка: {e}[/red]")

        if not user_input:
            console.print("[yellow]⏳ Нет команды[/yellow]")
            self.state = AgentState.IDLE
            return

        console.print(f"[yellow]📝 Команда: {user_input}[/yellow]")

        self.state = AgentState.THINKING
        console.print("[dim]🧠 Думаю...[/dim]")
        context = self.memory.get_context()
        messages = [
            {"role": "system", "content": (
                "Ты — UNI, голосовой помощник. Отвечай кратко и по делу. "
                "Управляешь XToys.app через команды: xtoys_toggle, xtoys_set_intensity, xtoys_select_pattern. "
                "Говори на русском.\n\nКонтекст:\n" + context
            )},
            {"role": "user", "content": user_input}
        ]
        response = await self.brain.chat(messages=messages, tools=get_tool_schemas())

        if response.text:
            console.print(f"[green]🗣️ {response.text}[/green]")
            speech = self.capabilities.get("speech")
            if speech:
                try:
                    await speech.speak(response.text)
                except Exception as e:
                    console.print(f"[red]❌ TTS ошибка: {e}[/red]")
        else:
            console.print("[dim]💭 (нет текста)[/dim]")

        if response.tool_calls:
            self.state = AgentState.EXECUTING
            for tc in response.tool_calls:
                console.print(f"[blue]🔧 {tc.name}({tc.arguments})[/blue]")
                result = await self.tool_executor.execute(tc.name, tc.arguments)
                if result.success:
                    console.print(f"[green]✅ {result.message}[/green]")
                    self.memory.set(f"last_{tc.name}", result.data or result.message)
                else:
                    console.print(f"[red]❌ {result.message}[/red]")

        if self.config.agent.verification_enabled:
            self.state = AgentState.VERIFYING
            console.print("[dim]🔍 Проверка...[/dim]")
            vision = self.capabilities.get("vision")
            if vision and self.config.capabilities.vision.enabled:
                try:
                    res = await vision.analyze_screen("Что изменилось?")
                    if res.success:
                        console.print(f"[dim]📸 {res.data[:100]}...[/dim]")
                except Exception as e:
                    console.print(f"[red]❌ Vision ошибка: {e}[/red]")

        self.state = AgentState.IDLE
        console.print("[bold green]✅ Готово[/bold green]")

    async def run_interactive(self):
        self._running = True
        console.print("[yellow]💬 Говорите команду (exit для выхода)[/yellow]")
        while self._running:
            try:
                speech = self.capabilities.get("speech")
                if speech:
                    user_input = await speech.listen(duration=5)
                    if user_input:
                        await self.run_cycle(user_input)
                else:
                    user_input = input("> ").strip()
                    if user_input.lower() in ("exit", "quit"):
                        break
                    if user_input:
                        await self.run_cycle(user_input)
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]⏹️ Стоп[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]❌ Ошибка: {e}[/red]")
