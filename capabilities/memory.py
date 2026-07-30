"""
uni.capabilities.memory — Capability-обёртка над WorkingMemory.

Назначение:
    Делает WorkingMemory доступной для Brain/Planner как обычную Capability
    (через единый Capability Protocol, зафиксированный в SUMMARY.md §5.4),
    чтобы LLM могла явно читать/писать память как tool-вызов, а не только
    неявно через get_context() в system prompt.

Зависимости:
    uni.working_memory.WorkingMemory
    uni.tools.results.ToolResult
    uni.config.MemoryConfig

Пример использования:
    >>> cap = MemoryCapability(cfg.memory)
    >>> await cap.setup()
    >>> await cap.memory_set(key="user_goal", value="найти видео про LM Studio")
    ToolResult(success=True, data={'key': 'user_goal'}, error=None, screenshot=None)

Известные ограничения:
    - setup()/shutdown() — no-op: WorkingMemory открывает/пишет файл
      синхронно и не держит долгоживущих соединений. Методы присутствуют
      только для соответствия Capability Protocol.
    - Регистрация в CapabilityRegistry (Build 4) сюда не входит — этот файл
      только определяет саму Capability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uni.config import MemoryConfig
from uni.tools.results import ToolResult
from uni.working_memory import WorkingMemory


class MemoryCapability:
    """Capability, оборачивающая WorkingMemory для вызова из Planner/LLM."""

    name: str = "memory"
    tools: list[str] = ["memory_set", "memory_get", "memory_delete", "memory_list_keys"]

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config
        self._wm = WorkingMemory(Path(config.path))

    async def setup(self) -> None:
        """No-op: WorkingMemory уже загружена в __init__."""
        return None

    async def shutdown(self) -> None:
        """No-op: нет открытых соединений, каждая запись уже атомарно persisted."""
        return None

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def memory_set(self, key: str, value: Any) -> ToolResult:
        try:
            self._wm.set(key, value)
            return ToolResult(success=True, data={"key": key})
        except Exception as e:  # noqa: BLE001 — ошибка Capability не должна ронять агент
            return ToolResult(success=False, error=str(e))

    async def memory_get(self, key: str, default: Any = None) -> ToolResult:
        try:
            return ToolResult(success=True, data=self._wm.get(key, default))
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))

    async def memory_delete(self, key: str) -> ToolResult:
        try:
            self._wm.delete(key)
            return ToolResult(success=True, data={"key": key})
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))

    async def memory_list_keys(self) -> ToolResult:
        try:
            return ToolResult(success=True, data=self._wm.list_keys())
        except Exception as e:  # noqa: BLE001
            return ToolResult(success=False, error=str(e))
