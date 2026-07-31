from uni.working_memory import WorkingMemory
from uni.contracts import ToolResult
from .base import Capability

class MemoryCapability(Capability):
    name = "memory"
    description = "Работа с памятью"

    def __init__(self, memory: WorkingMemory):
        self.memory = memory

    async def remember(self, key: str, value: str) -> ToolResult:
        self.memory.set(key, value)
        return ToolResult(success=True, message=f"Сохранено: {key}")

    async def recall(self, key: str) -> ToolResult:
        val = self.memory.get(key)
        if val is not None:
            return ToolResult(success=True, data=val, message=f"Найдено: {key}")
        return ToolResult(success=False, message=f"Ключ {key} не найден")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "remember":
            return await self.remember(kwargs.get("key", ""), kwargs.get("value", ""))
        elif action == "recall":
            return await self.recall(kwargs.get("key", ""))
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
