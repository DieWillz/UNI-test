"""
uni.agent — точка сборки агента (заглушка Build 1).

Назначение:
    Класс Agent — финальная точка сборки: держит Config, будет создавать
    CapabilityRegistry (Build 4), Brain (Build 2), WorkingMemory (Build 3),
    ToolExecutor (Build 9) и EventLoop (Build 10), и запускать run().

Зависимости:
    uni.config.Config

Пример использования (после Build 10):
    >>> cfg = load_config("config.yaml")
    >>> agent = Agent(cfg)
    >>> asyncio.run(agent.run())

Известные ограничения:
    Это ЗАГЛУШКА. Реальная сборка (wiring) всех компонентов происходит
    в Build 10 (DeepSeek, event_loop.py) и Build 12 (Claude, polish).
    Сейчас run() намеренно бросает NotImplementedError, чтобы никто
    не думал, что агент уже работает end-to-end.
"""

from __future__ import annotations

from uni.config import Config


class Agent:
    """Точка сборки агента. Полная реализация — Build 9/10/12."""

    def __init__(self, config: Config) -> None:
        self.config = config
        # Заполняется в последующих билдах:
        # self.brain: Brain | None = None                       (Build 2, DeepSeek)
        # self.memory: WorkingMemory | None = None               (Build 3, Claude)
        # self.capabilities: CapabilityRegistry | None = None    (Build 4, Claude)
        # self.executor: ToolExecutor | None = None               (Build 9, DeepSeek)
        # self.event_loop: EventLoop | None = None                (Build 10, DeepSeek)

    async def run(self) -> None:
        """Запускает бесконечный цикл агента. Реализуется в Build 10."""
        raise NotImplementedError(
            "Event loop ещё не подключён (Build 10, DeepSeek). "
            "Build 1 предоставляет только Config + скелет Agent."
        )
