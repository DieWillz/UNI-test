"""
uni.tools.results — единый формат результата выполнения tool.

Назначение:
    ToolResult зафиксирован координатором в SUMMARY.md §5.5 как формат,
    ОБЩИЙ для всех Capabilities (Nemotron: speech/computer/browser/vision;
    Claude: memory). Он нужен уже в Build 3 (Memory Capability wrapper),
    поэтому вынесен сюда, а не отложен до Build 4 (Tool Registry).

    uni/tools/definitions.py и uni/tools/registry.py (полный Build 4)
    будут импортировать ToolResult отсюда, а не определять заново.

Зависимости: pydantic

Известные ограничения:
    Расположение файла (uni/tools/results.py, а не uni/contracts.py или
    uni/tools/definitions.py) — моё решение как владельца инфраструктуры,
    контракт полей НЕ менялся. Прошу координатора подтвердить путь импорта
    в DECISION, чтобы DeepSeek (executors.py) и Nemotron (capabilities/*.py)
    использовали один и тот же `from uni.tools.results import ToolResult`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    screenshot: bytes | None = None
