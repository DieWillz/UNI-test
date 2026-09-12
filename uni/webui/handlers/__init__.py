"""UNI WebUI modular route registry.

New endpoints register here and are dispatched by ``uni.webui.server`` before
legacy branches. The registry must be importable while ``server`` itself is
still initializing, so handler modules must avoid importing server globals at
module import time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

Handler = Callable[[Any], None]


@dataclass
class Route:
    method: str
    path: str
    handler: Handler
    description: str = ""


class RouteRegistry:
    def __init__(self) -> None:
        self._routes: list[Route] = []

    def register(self, method: str, path: str, handler: Handler, description: str = "") -> Handler:
        self._routes.append(Route(method.upper(), path, handler, description))
        return handler

    def match(self, method: str, path: str) -> Handler | None:
        wanted = method.upper()
        for route in self._routes:
            if route.method == wanted and route.path == path:
                return route.handler
        for route in self._routes:
            if route.method == wanted and route.path.endswith("/*"):
                prefix = route.path[:-2]
                if path == prefix or path.startswith(prefix + "/"):
                    return route.handler
        return None

    def list_routes(self) -> list[dict[str, str]]:
        return [
            {"method": route.method, "path": route.path, "description": route.description}
            for route in self._routes
        ]


registry = RouteRegistry()


def _register_all() -> None:
    from . import app_status, events, health, memory_facts, mission, plugins, workspace  # noqa: F401


_register_all()
