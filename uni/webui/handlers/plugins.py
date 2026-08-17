"""Plugin discovery API (P-16, 2026-08-17)."""
from __future__ import annotations

from . import registry


def _list_plugins(handler) -> None:
    from uni.plugins import discover_plugins
    handler._json(200, {"plugins": discover_plugins()})


def _rediscover(handler) -> None:
    if handler.headers.get("Content-Length"):
        handler.rfile.read(int(handler.headers.get("Content-Length") or 0))
    from uni.plugins import discover_plugins, reset_cache
    reset_cache()
    handler._json(200, {"ok": True, "plugins": discover_plugins()})


registry.register("GET", "/api/plugins", _list_plugins, "список plugins")
registry.register("POST", "/api/plugins/discover", _rediscover, "пересканировать entry-points")
