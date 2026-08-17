"""SSE event hub (P-09, 2026-08-17).

Эндпоинт:
  GET /api/uni/events — SSE-поток событий от backend к frontend.

Использование:
  from uni.webui.handlers.events import publish_event
  publish_event({"type": "mission.updated", "mission": {...}})

Все клиенты SSE получают событие. Это убирает поллинг и даёт real-time
опыт чату и оверлею.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, List

from . import registry

_LOCK = threading.Lock()
_SUBSCRIBERS: List[queue.Queue] = []
_HISTORY: List[dict] = []
_HISTORY_MAX = 100


def publish_event(event: Dict[str, Any]) -> None:
    if "ts" not in event:
        event["ts"] = time.time()
    with _LOCK:
        _HISTORY.append(event)
        if len(_HISTORY) > _HISTORY_MAX:
            _HISTORY.pop(0)
        for q in _SUBSCRIBERS:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=200)
    with _LOCK:
        _SUBSCRIBERS.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _LOCK:
        try:
            _SUBSCRIBERS.remove(q)
        except ValueError:
            pass


def history_tail(n: int = 20) -> List[dict]:
    with _LOCK:
        return list(_HISTORY[-n:])


def _handle_events(handler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()

    q = subscribe()
    try:
        for ev in history_tail(20):
            try:
                handler.wfile.write(
                    f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8")
                )
                handler.wfile.flush()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                return
        while True:
            if getattr(handler.wfile, "closed", False):
                break
            try:
                conn_fd = handler.connection.fileno()
            except (OSError, ValueError):
                break
            if conn_fd < 0:
                break
            try:
                event = q.get(timeout=30.0)
            except queue.Empty:
                try:
                    handler.wfile.write(b": ping\n\n")
                    handler.wfile.flush()
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    break
                continue
            try:
                handler.wfile.write(
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                )
                handler.wfile.flush()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                break
    finally:
        unsubscribe(q)


registry.register("GET", "/api/uni/events", _handle_events, "SSE event hub (P-09)")
