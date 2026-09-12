"""Autonomous bridge (P-06, извлечено из event_loop.py).

Чистые функции для маршрутизации stop / manual intensity в hands-free
контроллер. Оригинальный _maybe_autonomous_override остаётся для
обратной совместимости.
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from .command_parser import is_stop_command


async def maybe_autonomous_override(
    *,
    user_input: str,
    controller: Any | None,
    run_tool: Callable[[str, dict[str, Any]], Awaitable[Any]],
    speak: Callable[[str], Awaitable[bool]],
) -> bool:
    """Если hands-free сессия активна — маршрутизирует stop / manual intensity.
    Возвращает True, если input потреблён контроллером.
    """
    if controller is None or not getattr(controller, "device_allowed", False):
        return False
    state = getattr(controller, "state", None)
    if state is not None and getattr(state, "stopped", False) and is_stop_command(user_input):
        return False
    if is_stop_command(user_input):
        controller.emergency_stop()
        return True
    m = re.search(r"(?:интенсивность|скорость|speed)\s*(\d{1,3})", user_input.casefold())
    if m:
        value = max(0, min(100, int(m.group(1))))
        res = await run_tool("xtoys.ramp_intensity", {"value": value, "steps": 3})
        if getattr(res, "success", False):
            state.intensity = value
            controller.request_manual_override(seconds=45.0)
            await speak(f"Приняла, поставила {value}%. Сама пока не трогаю — скажи, если снова управлять.")
            return True
    return False
