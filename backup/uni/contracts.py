"""
uni.contracts — общие структуры данных, разделяемые между модулями,
которые ещё не имеют собственного дома в дереве Build-ов.

Назначение:
    SUMMARY.md §5.5 фиксирует контракт ToolResult ("единый для всех tools"),
    но не указывает файл, где он должен жить. Capabilities (Build 3, 5-8)
    импортируют ToolResult раньше, чем появится uni/tools/executors.py
    (Build 9, DeepSeek). Чтобы не создавать циклический импорт
    "capabilities → tools → capabilities", ToolResult вынесен сюда —
    в модуль без зависимостей от capabilities/tools/brain.

    Build 9 (DeepSeek) должен импортировать ToolResult ИЗ этого модуля
    (`from uni.contracts import ToolResult`), а не определять повторно
    в uni/tools/executors.py.

Зависимости: только pydantic.

Известные ограничения:
    Размещение этого файла — моё архитектурное решение (Build 3), не
    зафиксированное явно в SUMMARY.md §5. Если координатор (Qwen) выберет
    другое расположение — потребуется один правкой обновить импорты
    в uni/capabilities/memory.py и последующих capability-модулях.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    screenshot: bytes | None = None