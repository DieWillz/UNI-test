from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .provider import build_provider, CouncilProvider

# Default participant registry. A participant is "free" when it is reachable through a
# Default participant registry. A participant is "free" when it is reachable through a
# local/free OpenAI-compatible endpoint; "paid" when it requires a closed web chat that
# we reach only through browser automation. The selection rule requested by the
# coordinator: prefer API when the model is free/available, fall back to browser when the
# API is paid/closed. Each participant has a fixed role in the consensus round.
# SECURITY / FAIR USE (MANIFESTO v2.6 §7):
# - No participant ever receives secrets. Browser transport uses a SEPARATE profile.
# - Advisor output is untrusted data; it is never executed nor used to call UNI tools.
# - Browser participants below target the FREE web tiers only (chatgpt.com free,
#   claude.ai free, x.com grok, gemini.google.com free). They must NEVER automate a
#   paid consumer subscription (ChatGPT Plus, Gemini Advanced, ...) as an API replacement.
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
        "transport": "browser",  # free web chat, no free API here
        "free_tier": True,  # chatgpt.com/claude.ai free tier, NOT a paid subscription
        "host": "claude.ai",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[aria-label='Send'], button[type='submit']",
        "answer_selector": "div[class*='response'], article",
    },
    {
        "name": "ChatGPT",
        "role": "General reviewer",
        "transport": "browser",
        "free_tier": True,
        "host": "chatgpt.com",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[data-testid='send-button'], button[type='submit']",
        "answer_selector": "div[class*='prose'], article",
    },
    {
        "name": "Grok",
        "role": "Reality-check / feasibility",
        "transport": "browser",
        "free_tier": True,
        "host": "x.com",  # grok lives inside x.com
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[type='submit']",
        "answer_selector": "div[class*='prose'], article",
    },
    {
        "name": "Gemini",
        "role": "Risk analyst",
        "transport": "browser",
        "free_tier": True,
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

    @property
    def is_free(self) -> bool:
        return self.transport == "api"

    @property
    def is_free_tier_browser(self) -> bool:
        """Browser participant that targets a FREE web tier (allowed by MANIFESTO v2.6 §7)."""
        return self.transport == "browser" and bool(self.spec.get("free_tier", False))

    def build_provider(self, *, browser_session=None, min_interval_seconds: float = 8.0) -> CouncilProvider:
        spec = dict(self.spec)
        if self.transport == "browser":
            if browser_session is None:
                raise ValueError(f"Participant {self.name} needs browser_session for browser transport")
            spec["browser_session"] = browser_session
            spec["min_interval_seconds"] = min_interval_seconds
        self.provider = build_provider(spec)
        return self.provider


def load_participants(
    specs: Optional[list[dict[str, Any]]] = None,
    *,
    browser_session=None,
    only: Optional[list[str]] = None,
    min_interval_seconds: float = 8.0,
) -> list[Participant]:
    """Build participant objects and their providers.

    `only` restricts to a named subset (useful for quick local-only rounds).
    A browser participant only gets a provider when a `browser_session` is supplied;
    otherwise the provider is left None and must be built later by the runner once it
    has started the browser (see run.py). This keeps load_participants importable and
    usable for API-only inspection without a live browser.
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
        if p.transport == "browser" and browser_session is None:
            # Defer provider creation until the runner supplies a browser session.
            pass
        else:
            p.build_provider(browser_session=browser_session, min_interval_seconds=min_interval_seconds)
        participants.append(p)
    return participants
