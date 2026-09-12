from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ProgressState(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    LOCATING = "LOCATING"
    TARGET_RESOLVED = "TARGET_RESOLVED"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class ProgressEvent:
    mission_id: str
    state: ProgressState
    step_id: str = ""
    action_id: str = ""
    detail: str = ""
    plan: tuple[tuple[str, str], ...] = ()


EventSink = Callable[[ProgressEvent], None]


def emit(sink: EventSink | None, event: ProgressEvent) -> None:
    """A synchronous, nonblocking observer; never used as verification evidence."""
    if sink is not None:
        try:
            sink(event)
        except Exception:
            # The observer is an untrusted extension boundary, not an executor.
            logging.getLogger(__name__).warning("Operator progress observer failed", exc_info=True)
