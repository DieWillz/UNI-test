"""UNI WebUI — модульный реестр эндпоинтов (P-03, 2026-08-17).

Сервер `uni.webui.server` исторически монолитный (~2600 строк). Полная
модуляризация требует итераций с тестами; вместо переписывания всего
сразу мы вводим **аддитивный registry**: новые эндпоинты регистрируются
здесь, а server.py проверяет registry ПЕРЕД своими legacy-ветвями.
Старые пути продолжают работать как fallback — поведение не меняется,
но новые endpoints живут в отдельных файлах, их легче тестировать и
ревьюить.

Миграция существующих endpoints в handlers/ — отдельная итерация
(Директива MODULAR-02).

Использование:
    from uni.webui import handlers
    handlers.registry.match("GET", "/api/uni/health") -> handler_func | None

    # в server.py:
    handler = handlers.registry.match(method, path)
    if handler:
        handler(self); return
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List

Handler = Callable[[Any], None]


@dataclass
class Route:
    method: str
    path: str            # точное совпадение ИЛИ префикс (заканчивается на "/*")
    handler: Handler
    description: str = ""


class RouteRegistry:
    """Минимальный роутер: точный match, затем префиксный (/*), иначе None."""

    def __init__(self) -> None:
        self._routes: List[Route] = []

    def register(
        self,
        method: str,
        path: str,
        handler: Handler,
        description: str = "",
    ) -> Handler:
        self._routes.append(Route(method.upper(), path, handler, description))
        return handler

    def match(self, method: str, path: str) -> Handler | None:
        m = method.upper()
        for r in self._routes:
            if r.method == m and r.path == path:
                return r.handler
        for r in self._routes:
            if r.method == m and r.path.endswith("/*"):
                prefix = r.path[:-2]
                if path == prefix or path.startswith(prefix + "/"):
                    return r.handler
        return None

    def list_routes(self) -> List[dict]:
        return [
            {"method": r.method, "path": r.path, "description": r.description}
            for r in self._routes
        ]


registry = RouteRegistry()


def _register_all() -> None:
    from . import (
        health,
        mission,
        memory_facts,
        plugins,
        events,
    )  # noqa: F401  — модули саморегистрируются при импорте


_register_all()
