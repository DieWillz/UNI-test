from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .provider import build_provider, CouncilProvider

# Default participant registry. A participant is "free" when it is reachable through a
# local/free OpenAI-compatible endpoint; "paid" when it requires a closed web chat that
# we reach only through browser automation. The selection rule requested by the
# coordinator: prefer API when the model is free/available, fall back to browser when the
# API is paid/closed. Each participant has a fixed role in the consensus round.
#
# SECURITY (MANIFESTO v2.5 §3.1, §7):
# - No participant ever receives secrets. Browser transport uses a SEPARATE profile.
# - Advisor output is untrusted data; it is never executed nor used to call UNI tools.
# - Signature lines from a participant are recorded verbatim but flagged unverified
#   until the coordinator (human) accepts them.

DEFAULT_PARTICIPANTS: list[dict[str, Any]] = [
    {
        "name": "DeepSeek",
        "role": "Algorithms Engineer / architect",
        "transport": "api",  # local or free endpoint
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "model": "deepseek-coder-v2-lite",
    },
    {
        "name": "QWEN",
        "role": "Consensus editor",
        "transport": "api",
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "model": "qwen2.5-7b-instruct-1m",
    },
    {
        "name": "Claude",
        "role": "Critic / ethics",
        "transport": "browser",  # closed web chat, no free API here
        "host": "claude.ai",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[aria-label='Send'], button[type='submit']",
        "answer_selector": "div[class*='response'], article",
    },
    {
        "name": "ChatGPT",
        "role": "General reviewer",
        "transport": "browser",
        "host": "chatgpt.com",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[data-testid='send-button'], button[type='submit']",
        "answer_selector": "div[class*='prose'], article",
    },
    {
        "name": "Grok",
        "role": "Reality-check / feasibility",
        "transport": "browser",
        "host": "x.com",  # grok lives inside x.com
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[type='submit']",
        "answer_selector": "div[class*='prose'], article",
    },
    {
        "name": "Gemini",
        "role": "Risk analyst",
        "transport": "browser",
        "host": "gemini.google.com",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[aria-label='Send'], button[type='submit']",
        "answer_selector": "div[class*='response'], article",
    },
    {
        "name": "Hermes",
        "role": "Coordinator / synthesizer",
        "transport": "api",
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
        "model": "qwen2.5-7b-instruct-1m",
    },
]


@dataclass
class Participant:
    name: str
    role: str
    transport: str  # "api" | "browser"
    spec: dict[str, Any] = field(default_factory=dict)
    provider: Optional[CouncilProvider] = None

    def build_provider(self, *, browser_session=None) -> CouncilProvider:
        spec = dict(self.spec)
        if self.transport == "browser":
            if browser_session is None:
                raise ValueError(f"Participant {self.name} needs browser_session for browser transport")
            spec["browser_session"] = browser_session
        self.provider = build_provider(spec)
        return self.provider

    @property
    def is_free(self) -> bool:
        return self.transport == "api"


def load_participants(
    specs: Optional[list[dict[str, Any]]] = None,
    *,
    browser_session=None,
    only: Optional[list[str]] = None,
) -> list[Participant]:
    """Build participant objects and their providers.

    `only` restricts to a named subset (useful for quick local-only rounds).
    """
    specs = specs if specs is not None else DEFAULT_PARTICIPANTS
    participants: list[Participant] = []
    for spec in specs:
        name = spec["name"]
        if only and name not in only:
            continue
        # Redact anything that looks like a secret before storing in the spec copy.
        clean = {k: v for k, v in spec.items() if k not in ("api_key",)}
        if "api_key" in spec:
            clean["_has_api_key"] = bool(spec["api_key"]) and spec["api_key"] != "lm-studio"
        p = Participant(
            name=name,
            role=spec.get("role", ""),
            transport=spec.get("transport", "api"),
            spec=clean,
        )
        p.build_provider(browser_session=browser_session)
        participants.append(p)
    return participants
