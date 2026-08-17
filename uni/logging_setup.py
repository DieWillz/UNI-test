"""Structured logging setup (P-14, 2026-08-17).

JSON formatter + contextvar-based trace_id для корреляции событий
в одном цикле EventLoop. Опционально; включается env-флагом
UNI_LOG_FORMAT=json или вызовом setup_logging("json").

Использование:
  from uni.logging_setup import setup_logging, with_trace
  setup_logging("json")
  with with_trace("mission-123"):
      logger.info("started", extra={"stage": "research"})

Output:
  {"ts":"2026-08-17T10:00:00Z","level":"INFO","logger":"uni.mission",
   "trace_id":"mission-123","message":"started","stage":"research"}
"""
from __future__ import annotations

import contextlib
import json
import logging
import time
from contextvars import ContextVar
from typing import Iterator

_TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    return _TRACE_ID.get("")


@contextlib.contextmanager
def with_trace(trace_id: str) -> Iterator[None]:
    """Устанавливает trace_id для блока кода."""
    token = _TRACE_ID.set(trace_id)
    try:
        yield
    finally:
        _TRACE_ID.reset(token)


class JsonFormatter(logging.Formatter):
    """JSON-форматтер с trace_id."""

    def format(self, record: logging.LogRecord) -> str:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": _TRACE_ID.get(""),
            "message": record.getMessage(),
        }
        # extra fields (из logger.info(..., extra={...}))
        for k, v in record.__dict__.items():
            if k in ("msg", "args", "name", "levelname", "levelno", "pathname",
                     "filename", "module", "exc_info", "exc_text", "stack_info",
                     "lineno", "funcName", "created", "msecs", "relativeCreated",
                     "thread", "threadName", "processName", "process", "message"):
                continue
            try:
                json.dumps(v)
                rec[k] = v
            except TypeError:
                rec[k] = repr(v)
        if record.exc_info:
            rec["exception"] = self.formatException(record.exc_info)
        return json.dumps(rec, ensure_ascii=False)


_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s"


class _TraceFilter(logging.Filter):
    """Инжектит trace_id в record для text-форматтера."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _TRACE_ID.get("")  # type: ignore[attr-defined]
        return True


def setup_logging(format: str = "text", level: int | str = logging.INFO) -> None:
    """Настраивает корневой логгер.

    format: 'text' (default, human) или 'json' (structured).
    """
    root = logging.getLogger()
    root.setLevel(level)
    # убираем старые handlers, чтобы не дублировать
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
        handler.addFilter(_TraceFilter())
    root.addHandler(handler)
