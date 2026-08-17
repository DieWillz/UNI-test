"""Screen watch loop (P-06, извлечено из event_loop.py).

Event-driven наблюдение за экраном: VLM включается ТОЛЬКО при изменении
(cheap image hash). Чистая async-функция.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


_SENSITIVE_URL_HINTS = (
    "password", "account/login", "online-bank", "bank", "telegram",
    "web.whatsapp", "mail", "private", "auth", "signin",
)


def is_sensitive_url(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _SENSITIVE_URL_HINTS)


def screenshot_hash(path: str | None) -> str:
    if not path:
        return ""
    try:
        import imagehash
        from PIL import Image
        return str(imagehash.average_hash(Image.open(path)))
    except Exception:
        try:
            from pathlib import Path
            return str(Path(path).stat().st_size)
        except Exception:
            return ""


async def watch_screen_loop(
    *,
    interval: float,
    stop_event: asyncio.Event,
    run_tool: Callable[[str, dict[str, Any]], Awaitable[Any]],
    speak: Callable[[str], Awaitable[bool]],
    log: Callable[[str, Any], None] | None = None,
    on_change: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> None:
    """Основной цикл наблюдения. Останавливается по stop_event."""
    prev_hash = ""
    while not stop_event.is_set():
        tab = await run_tool("browser.current_tab", {})
        if getattr(tab, "success", False) and isinstance(getattr(tab, "data", None), dict):
            url = str(tab.data.get("url", ""))
            if is_sensitive_url(url):
                await asyncio.sleep(interval)
                continue
        shot = await run_tool("browser.save_screenshot", {"label": "watch"})
        if getattr(shot, "success", False) and isinstance(getattr(shot, "data", None), dict):
            h = screenshot_hash(shot.data.get("path"))
            if h and h != prev_hash:
                prev_hash = h
                analysis = await run_tool("vision.analyze_screen", {
                    "prompt": "Кратко опиши, что изменилось на экране (максимум 2 предложения).",
                })
                if getattr(analysis, "success", False):
                    observation = {
                        "timestamp": asyncio.get_running_loop().time(),
                        "confidence": 0.5,
                        "analysis": getattr(analysis, "message", ""),
                    }
                    if on_change is not None:
                        await on_change(observation)
                    await speak(getattr(analysis, "message", ""))
        await asyncio.sleep(interval)
