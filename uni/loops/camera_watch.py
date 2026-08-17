"""Camera watch loop (P-06, извлечено из event_loop.py).

Чистая async-функция, не зависит от self EventLoop — принимает run_tool,
speak и log как параметры. Тестируется изолированно.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def camera_watch_worker(
    *,
    duration_s: float,
    min_brightness: float,
    sample_interval_seconds: float,
    reminder_interval_seconds: float,
    run_tool: Callable[[str, dict[str, Any]], Awaitable[Any]],
    speak: Callable[[str], Awaitable[bool]],
    log: Callable[[str, Any], None] | None = None,
) -> None:
    """Наблюдение через камеру с периодическими снимками и звуковыми напоминаниями."""
    started_at = asyncio.get_running_loop().time()
    ends_at = started_at + duration_s
    next_sample = started_at
    next_reminder = started_at + reminder_interval_seconds
    completed_normally = False
    try:
        while True:
            now = asyncio.get_running_loop().time()
            if now >= ends_at:
                completed_normally = True
                break
            if now >= next_sample:
                frame = await run_tool("camera.snapshot", {"label": "watch"})
                if getattr(frame, "success", False) and isinstance(getattr(frame, "data", None), dict):
                    path = str(frame.data.get("path", ""))
                    brightness = float(frame.data.get("brightness", 0.0))
                    if log:
                        log("CAMERA_FRAME", f"{path} brightness={brightness:.2f}")
                    if brightness < min_brightness:
                        if log:
                            log("CAMERA_OBSERVATION", "Кадр слишком тёмный для надёжного анализа")
                    else:
                        analysis = await run_tool("vision.analyze_file", {
                            "path": path,
                            "prompt": (
                                "Briefly describe this room webcam frame and any visible change or unusual event. "
                                "Do not infer identity or facts outside the image."
                            ),
                        })
                        if getattr(analysis, "success", False) and isinstance(getattr(analysis, "data", None), dict):
                            if log:
                                log("CAMERA_OBSERVATION", analysis.data.get("analysis", ""))
                next_sample = now + sample_interval_seconds
            if now >= next_reminder:
                await speak("Напоминаю: я всё ещё наблюдаю через камеру.")
                if log:
                    log("CAMERA_NOTICE", "Периодическое звуковое напоминание")
                next_reminder = now + reminder_interval_seconds
            delay = min(1.0, max(0.05, ends_at - now), max(0.05, next_sample - now), max(0.05, next_reminder - now))
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        raise
    finally:
        await run_tool("camera.stop", {})
        if completed_normally:
            if log:
                log("CAMERA_NOTICE", "Длительное наблюдение завершено")
            await speak("Я закончила наблюдение и выключила камеру.")
