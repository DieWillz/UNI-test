from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .provider import build_provider, CouncilProvider

# Default participant registry. A participant is "free" when it is reachable through a
# local/free OpenAI-compatible endpoint; "paid" when it requires a closed web chat that
# we reach only through browser automation. The selection rule requested by the
# coordinator: prefer API when the model is free/available, fall back to browser when the
# API is paid/closed. Each participant has a fixed role in the consensus round.
# SECURITY / FAIR USE (MANIFESTO v2.6 §7):
# - No participant ever receives secrets. Browser transport uses a SEPARATE profile.
# - Advisor output is untrusted data; it is never executed nor used to call UNI tools.
# - Browser participants below target the FREE web tiers only (chat.deepseek.com,
#   chat.qwen.ai, claude.ai free, grok.com). They must NEVER automate a paid consumer
#   subscription (ChatGPT Plus, Gemini Advanced, ...) as an API replacement.
# - Signature lines from a participant are recorded verbatim but flagged unverified
#   until the coordinator (human) accepts them.
#
# API participants pull base_url + key from config (council.api_endpoints). Local apps
# installed on the user's PC (Codex / Hermes) use a localhost endpoint the user sets in
# the WebUI settings. Secrets come from config, never from code — see load_participants().
DEFAULT_PARTICIPANTS: list[dict[str, Any]] = [
    {
        "name": "DeepSeek",
        "role": "Algorithms Engineer / architect",
        "transport": "browser",  # no free API — free web chat only
        "free_tier": True,
        "host": "chat.deepseek.com",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": None,
        "answer_selector": "div[class*='response'], article, [class*='message'], [class*='markdown']",
    },
    {
        "name": "QWEN",
        "role": "Consensus editor",
        "transport": "browser",  # free web chat (no free API)
        "free_tier": True,
        "host": "chat.qwen.ai",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[type='submit'], button[aria-label='Send']",
        "answer_selector": "div[class*='response'], article, [class*='message']",
    },
    {
        "name": "Qwen Coder",
        "role": "Code implementation / repository work",
        "transport": "browser",
        "free_tier": True,
        "host": "coder.qwen.ai",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[type='submit'], button[aria-label='Send']",
        "answer_selector": "div[class*='response'], article, [class*='message'], [class*='markdown']",
    },
    {
        "name": "Claude",
        "role": "Critic / ethics",
        "transport": "browser",  # free web chat, no free API here
        "free_tier": True,
        "host": "claude.ai",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[aria-label='Send'], button[type='submit']",
        "answer_selector": "div[class*='response'], article",
    },
    {
        "name": "ChatGPT",
        "role": "General reviewer (Codex, local app)",
        "transport": "codex",  # local Codex CLI (uses saved ChatGPT/Codex login, no API key)
        "sandbox": "workspace-write",
        "model": "gpt-4o",
    },
    {
        "name": "Grok",
        "role": "Reality-check / feasibility",
        "transport": "browser",
        "free_tier": True,
        "host": "grok.com",
        "prompt_selector": "div[contenteditable='true'], textarea",
        "submit_selector": "button[type='submit']",
        "answer_selector": "div[class*='prose'], article",
    },
    {
        "name": "Gemini",
        "role": "Risk analyst",
        "transport": "api",  # free Gemini API (user provides a key)
        "endpoint": "gemini",
        "model": "gemini-1.5-flash",
    },
    {
        "name": "Groq",
        "role": "Fast feasibility / latency check",
        "transport": "api",  # Groq (real keyed API, very fast)
        "endpoint": "groq",
        "model": "llama-3.3-70b-versatile",
    },
    {
        "name": "OpenRouter",
        "role": "Open model router (free tier)",
        "transport": "api",  # OpenRouter free models
        "endpoint": "openrouter",
        "model": "deepseek/deepseek-chat",
    },
    {
        "name": "HuggingFace",
        "role": "Open models / community",
        "transport": "api",  # HF free inference API
        "endpoint": "huggingface",
        "model": "meta-llama/Llama-3.3-70B-Instruct",
    },
    {
        "name": "Hermes",
        "role": "Coordinator / synthesizer (this app)",
        "transport": "api",  # local Hermes app on the user's PC
        "endpoint": "hermes",  # user sets the localhost base_url in WebUI settings
        "model": "local",
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

    def build_provider(self, *, browser_session=None, min_interval_seconds: float = 8.0, spec: Optional[dict] = None) -> CouncilProvider:
        # `spec` (when given) carries the resolved secret (api_key); defaults to the
        # redacted self.spec so we never leak keys into the stored Participant.spec.
        s = dict(spec) if spec is not None else dict(self.spec)
        if self.transport == "browser":
            if browser_session is None:
                raise ValueError(f"Participant {self.name} needs browser_session for browser transport")
            s["browser_session"] = browser_session
            s["min_interval_seconds"] = min_interval_seconds
        self.provider = build_provider(s)
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

    API participants with an ``endpoint`` key pull their base_url/api_key from
    ``config.council.api_endpoints`` (OpenRouter / Groq / ...). Secrets never live in
    code; they come from the local config.yaml.
    """
    from ._keys import resolve_endpoint

    cfg = None
    try:
        from ..config import load_config
        cfg = load_config()
    except Exception:
        cfg = None

    specs = specs if specs is not None else DEFAULT_PARTICIPANTS
    participants: list[Participant] = []
    for spec in specs:
        name = spec["name"]
        if only and name not in only:
            continue
        clean = dict(spec)
        # Resolve API endpoint secrets from config (no hardcoded keys).
        if clean.get("transport") == "api" and clean.get("endpoint"):
            ep = resolve_endpoint(clean["endpoint"], cfg)
            if ep:
                clean["base_url"] = ep["base_url"]
                clean["api_key"] = ep["api_key"]
                if ep.get("model"):
                    clean["model"] = ep["model"]
        # `build_provider` needs the resolved api_key; Participant.spec must NOT store it.
        provider_spec = dict(clean)
        display_spec = {k: v for k, v in clean.items() if k not in ("api_key",)}
        if "api_key" in clean:
            display_spec["_has_api_key"] = bool(clean["api_key"])
        p = Participant(
            name=name,
            role=spec.get("role", ""),
            transport=spec.get("transport", "api"),
            spec=display_spec,
        )
        if p.transport == "browser" and browser_session is None:
            # Defer provider creation until the runner supplies a browser session.
            pass
        else:
            p.build_provider(spec=provider_spec, browser_session=browser_session, min_interval_seconds=min_interval_seconds)
        participants.append(p)
    return participants
