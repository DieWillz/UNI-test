from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


class ContextBudgetExceeded(ValueError):
    """Essential task context cannot be represented within the request budget."""


def conservative_tokens(text: str) -> int:
    """UTF-8 byte bound for byte-level tokenizers; inject the model counter if known.

    This deliberately avoids chars/4 estimates for Cyrillic, code and emoji.
    Chat framing is reserved separately; this is not a measured model token count.
    """
    return len(text.encode("utf-8"))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ContextBudget:
    context_tokens: int = 5120
    output_tokens: int = 900
    framing_tokens: int = 128
    count: Callable[[str], int] = conservative_tokens

    def __post_init__(self) -> None:
        if (self.output_tokens <= 0 or self.framing_tokens < 0
                or self.input_tokens <= 0):
            raise ValueError("invalid_planner_context_budget")

    @property
    def input_tokens(self) -> int:
        return self.context_tokens - self.output_tokens - self.framing_tokens

    def fits(self, system: str, payload: dict[str, Any]) -> bool:
        return self.count(system) + self.count(compact_json(payload)) <= self.input_tokens

    def pack(self, system: str, *, goal: str, state: dict[str, Any],
             actions: list[dict[str, Any]], elements: list[dict[str, Any]],
             failure: str = "", repair: str = "",
             requirements: dict[str, Any] | None = None) -> list[dict[str, str]]:
        # Goal, current identity and supplied completion requirements are atomic.
        # Oversized essentials are rejected rather than silently truncated.
        payload: dict[str, Any] = {
            "goal": goal, "current_state": state,
            "requirements": requirements or {}, "allowed_actions": [],
            "scene_elements": [], "omitted_actions": len(actions),
            "omitted_elements": len(elements),
        }
        if not self.fits(system, payload):
            raise ContextBudgetExceeded("planner_essential_context_exceeds_budget")

        # Reserve relevant semantic targets before optional catalog breadth.
        # At most one quarter of available input is spent here.
        selected: list[dict[str, Any]] = []
        for element in elements[:8]:
            if self.count(compact_json([*selected, element])) > self.input_tokens // 4:
                continue
            payload["scene_elements"].append(element)
            payload["omitted_elements"] -= 1
            if not self.fits(system, payload):
                payload["scene_elements"].pop()
                payload["omitted_elements"] += 1
                continue
            selected.append(element)

        # Action arguments precede optional scene detail. Never send partial schemas.
        for action in actions:
            payload["allowed_actions"].append(action)
            payload["omitted_actions"] -= 1
            if not self.fits(system, payload):
                payload["allowed_actions"].pop()
                payload["omitted_actions"] += 1
        if not payload["allowed_actions"]:
            raise ContextBudgetExceeded("planner_action_catalog_exceeds_budget")
        for element in elements:
            if element in selected:
                continue
            payload["scene_elements"].append(element)
            payload["omitted_elements"] -= 1
            if not self.fits(system, payload):
                payload["scene_elements"].pop()
                payload["omitted_elements"] += 1
        # Failure/format-repair are bounded diagnostic strings, never chat history.
        for key, text in (("recent_failure", failure), ("format_error", repair)):
            if not text:
                continue
            payload[key] = text[:800]
            while payload[key] and not self.fits(system, payload):
                payload[key] = payload[key][:len(payload[key]) // 2]
            if not payload[key]:
                del payload[key]
        if not self.fits(system, payload):
            raise ContextBudgetExceeded("planner_context_exceeds_budget")
        return [{"role": "system", "content": system},
                {"role": "user", "content": compact_json(payload)}]
