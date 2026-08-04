"""Resolve API endpoint secrets for council participants from the local config.

Secrets NEVER live in code — they are read from ``config.council.api_endpoints``
which is populated from the user's local config.yaml (edited via the WebUI settings
panel). This module is the single place that maps an endpoint name (e.g. "openrouter")
to its (base_url, api_key).
"""
from __future__ import annotations

from typing import Any, Optional

_ENDPOINT_FALLBACKS: dict[str, dict[str, str]] = {
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "groq": {"base_url": "https://api.groq.com/openai/v1"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"},
    "huggingface": {"base_url": "https://router.huggingface.co/v1"},
    "codex": {"base_url": "http://localhost:1240/v1"},  # local Codex app (user sets port)
    "hermes": {"base_url": "http://localhost:8000/v1"},  # local Hermes app (user sets port)
}


def resolve_endpoint(name: str, cfg: Any = None) -> Optional[dict[str, str]]:
    """Return {'base_url', 'api_key'[, 'model']} for an endpoint name from config, else None.

    Falls back to a known base_url when config is unavailable, but the api_key must
    come from config (never a hardcoded default secret). An optional ``model`` key in
    the config entry overrides the participant registry default (e.g. pinning a
    ``:free`` OpenRouter model or the local LM Studio model id).
    """
    fallback = dict(_ENDPOINT_FALLBACKS.get(name, {}))
    if cfg is not None:
        endpoints = getattr(getattr(cfg, "council", None), "api_endpoints", None) or {}
        entry = endpoints.get(name)
        if isinstance(entry, dict):
            base = entry.get("base_url") or fallback.get("base_url")
            key = entry.get("api_key") or ""
            if base:
                resolved = {"base_url": base, "api_key": key}
                if entry.get("model"):
                    resolved["model"] = str(entry["model"])
                return resolved
    if fallback:
        return {"base_url": fallback["base_url"], "api_key": ""}
    return None
