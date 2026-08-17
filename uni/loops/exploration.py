"""Web exploration loop (P-06, извлечено из event_loop.py)."""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable


async def next_exploration_query(
    *,
    brain_chat: Callable[..., Awaitable[Any]],
    current: str,
    observation: str,
    step: int,
) -> tuple[str, str]:
    """Выбирает следующий безопасный шаг любознательного поиска."""
    response = await brain_chat(
        [
            {
                "role": "system",
                "content": (
                    "Ты выбираешь следующий безопасный шаг любознательного поиска по изображениям. "
                    "Не предлагай вход, формы, покупки, скачивания, взрослый контент или изменение сайтов. "
                    "Верни только JSON: {\"thought\": \"краткая мысль вслух\", "
                    "\"next_query\": \"следующий поисковый запрос\"}. Это публичное резюме, не скрытая цепочка рассуждений."
                ),
            },
            {
                "role": "user",
                "content": f"Шаг {step}. Текущий запрос: {current}. Наблюдение: {observation[:1800]}",
            },
        ],
        tools=None, temperature=0.6, max_tokens=180,
    )
    fallback = (f"{current} сравнение размеров", f"Интересно сравнить изображения по теме «{current}».")
    if getattr(response, "error", None) or not getattr(response, "text", None):
        return fallback
    try:
        raw = response.text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
        data = json.loads(fenced.group(1) if fenced else raw)
        query = str(data.get("next_query", "")).strip()[:180]
        thought = str(data.get("thought", "")).strip()[:500]
        if not query or not thought:
            return fallback
        return query, thought
    except (ValueError, TypeError, json.JSONDecodeError):
        return fallback


async def explore_web(
    *,
    topic: str,
    exploration_steps: int,
    run_tool: Callable[[str, dict[str, Any]], Awaitable[Any]],
    speak: Callable[[str], Awaitable[bool]],
    brain_chat: Callable[..., Awaitable[Any]],
    log: Callable[[str, Any], None] | None = None,
) -> str:
    query = topic.strip()[:180] or "необычные природные явления"
    summaries: list[str] = []
    for step in range(1, exploration_steps + 1):
        thought = f"Шаг {step}: ищу изображения по теме «{query}»."
        if log:
            log("THOUGHT", thought)
        await speak(thought)
        search_result = await run_tool("browser.search_images", {"query": query})
        if not getattr(search_result, "success", False):
            return f"Исследование остановлено: {getattr(search_result, 'message', '')}"
        screenshot_result = await run_tool("browser.save_screenshot", {"label": f"explore_{step}_{query[:40]}"})
        observation_result = await run_tool("vision.analyze_screen", {
            "prompt": "Кратко опиши видимые результаты поиска изображений и назови самое интересное безопасное направление для продолжения.",
        })
        observation = getattr(observation_result, "message", "")
        summaries.append(observation[:500])
        if getattr(screenshot_result, "success", False) and isinstance(getattr(screenshot_result, "data", None), dict):
            if log:
                log("SCREENSHOT", screenshot_result.data.get("path", ""))
        if step < exploration_steps:
            query, next_thought = await next_exploration_query(
                brain_chat=brain_chat, current=query, observation=observation, step=step,
            )
            if log:
                log("THOUGHT", next_thought)
            await speak(next_thought)
    return f"Исследование завершено за {len(summaries)} шага. Скриншоты и журнал сохранены в папке сессии."
