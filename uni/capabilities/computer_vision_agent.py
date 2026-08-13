"""Замкнутый цикл зрение -> решение -> действие -> проверка (P1.1 / D1).

ВАЖНО: не импортирует capability напрямую (ADR-0005) — все вызовы идут
через ToolExecutor (vision.* / computer.*). Это держит слабую связь и
позволяет подменять исполнителя в тестах (mock-LLM).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from uni.contracts import ToolResult

logger = logging.getLogger(__name__)


class ComputerVisionAgent:
    def __init__(self, tool_executor, max_steps: int = 8) -> None:
        self.tool_executor = tool_executor
        self.max_steps = max(2, int(max_steps))

    async def act_on_screen(self, goal: str, max_steps: int | None = None) -> dict:
        """Цикл: скриншот -> анализ (VLM) -> действие -> (проверка).

        Возвращает {"status": "success"|"failed", "steps": [...], "error": str}.
        """
        steps: list[dict[str, Any]] = []
        n = max_steps or self.max_steps
        for step in range(n):
            # 1. скриншот ДО (доступен для внешней сверки)
            await self.tool_executor.execute(
                "vision.capture_screen_png", {"label": f"cva_before_{step}"}
            )
            # 2. анализ экрана -> JSON-действие
            analysis = await self.tool_executor.execute(
                "vision.analyze_desktop",
                {
                    "prompt": (
                        f"{goal}. Верни СТРОГО JSON без другого текста: "
                        '{"action": "click"|"move"|"type", "x": int, "y": int, "text": str}.'
                    )
                },
            )
            action_data = self._parse_action(analysis)
            if action_data is None:
                return {"status": "failed", "error": "Некорректный ответ Vision", "steps": steps}
            # 3. действие
            act = action_data.get("action")
            try:
                if act in ("click", "move"):
                    x, y = int(action_data["x"]), int(action_data["y"])
                    res = await self.tool_executor.execute("computer.click", {"x": x, "y": y})
                    steps.append({"action": act, "x": x, "y": y, "ok": res.success})
                elif act == "type":
                    text = str(action_data.get("text", ""))
                    res = await self.tool_executor.execute("computer.type_text", {"text": text})
                    steps.append({"action": "type", "text": text, "ok": res.success})
                else:
                    return {"status": "failed", "error": f"Неизвестное действие: {act}", "steps": steps}
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                return {"status": "failed", "error": f"Ошибка действия: {exc}", "steps": steps}
            # 4. проверка: скриншот ПОСЛЕ (доступен для сравнения оператору)
            await self.tool_executor.execute(
                "vision.capture_screen_png", {"label": f"cva_after_{step}"}
            )
            # простая эвристика успеха: все шаги исполнены
            if steps and all(s.get("ok") for s in steps):
                return {"status": "success", "steps": steps}
        return {"status": "failed", "error": f"Цель не достигнута за {n} шагов", "steps": steps}

    @staticmethod
    def _parse_action(result: ToolResult) -> dict | None:
        if not result.success or not isinstance(result.data, dict):
            return None
        text = str(result.data.get("analysis") or "")
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
            return None
