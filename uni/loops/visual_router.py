"""Visual command router (P-06, извлечено из event_loop.py).

Чистая функция: текст + capabilities -> ответ | None.
Оригинальный _try_visual_command() остаётся для обратной совместимости.
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable


_VISUAL_RE = re.compile(
    r"^\s*(?:кликни\s+(?:по|на)|открой|кликни|нажми|запусти|включи|щёлкни|открыть|нажать)\b[\s:,-]*(.+)$",
    re.IGNORECASE,
)


def match_visual_goal(text: str) -> str | None:
    """Возвращает цель для управления ПК под зрением, или None."""
    if not text:
        return None
    m = _VISUAL_RE.match(text)
    if not m:
        return None
    goal = m.group(1).strip().strip(".,!")
    return goal or None


async def route_visual_command(
    text: str,
    act_on_screen: Callable[[str], Awaitable[dict[str, Any]]] | None,
) -> str | None:
    """Если фраза — команда управления ПК под зрением, выполняет и возвращает ответ.
    Иначе None (передать обычному LLM-циклу).
    """
    goal = match_visual_goal(text)
    if goal is None or act_on_screen is None:
        return None
    try:
        result = await act_on_screen(goal)
    except Exception as exc:
        return f"Ошибка управления ПК: {type(exc).__name__}: {exc}"
    status = result.get("status", "failed") if isinstance(result, dict) else "failed"
    if status == "verified":
        return f"Готово: {goal}."
    if status == "not_verified":
        return f"Действие выполнено, но результат не подтверждён: {goal}."
    if status == "blocked":
        return f"Команда заблокирована: {(result or {}).get('error', '')}"
    if status == "interrupted":
        return "Остановлено по команде СТОП."
    if status == "clarify":
        return "Не уверена, где это на экране — уточните цель."
    return f"Не получилось выполнить «{goal}»: {(result or {}).get('error', '')}"
