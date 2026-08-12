from __future__ import annotations

from typing import Any


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def get_all_tool_definitions(enabled_capabilities: set[str] | None = None) -> list[dict[str, Any]]:
    definitions: list[tuple[str, dict[str, Any]]] = [
        ("xtoys", _tool("xtoys_open", "Открыть и выбрать вкладку XToys.app", {})),
        ("xtoys", _tool("xtoys_toggle", "Нажать кнопку подключения или включения устройства XToys", {"device": {"type": "string"}})),
        ("xtoys", _tool("xtoys_set_intensity", "Установить интенсивность устройства XToys", {"device": {"type": "string"}, "value": {"type": "integer", "minimum": 0, "maximum": 100}}, ["value"])),
        ("xtoys", _tool("xtoys_select_pattern", "Выбрать паттерн XToys", {"device": {"type": "string"}, "pattern": {"type": "string"}}, ["pattern"])),
        ("xtoys", _tool("xtoys_get_status", "Прочитать видимое состояние вкладки XToys", {"device": {"type": "string"}})),
        ("xtoys", _tool("xtoys_motion_start", "Запустить управление машинкой по движению в выбранной области экрана", {"region": {"type": "object"}, "threshold": {"type": "number"}, "gain": {"type": "number"}, "smoothing": {"type": "number"}, "gamma": {"type": "number"}, "period_ms": {"type": "integer"}, "max_intensity": {"type": "number"}}, ["region"])),
        ("xtoys", _tool("xtoys_motion_stop", "Безопасно остановить управление машинкой по движению", {})),
        ("xtoys", _tool("xtoys_motion_status", "Получить состояние Motion-to-Toy без запуска устройства", {})),
        ("xtoys", _tool("xtoys_remote_session_start", "Создать временную удалённую сессию управления после явной просьбы владельца", {"max_intensity": {"type": "number", "minimum": 0, "maximum": 100}, "ttl": {"type": "number", "minimum": 60, "maximum": 3600}}, ["max_intensity"])),
        ("xtoys", _tool("xtoys_remote_session_stop", "Закрыть удалённую сессию и остановить устройство", {})),
        ("xtoys", _tool("xtoys_remote_status", "Получить безопасный статус удалённой сессии без токена", {})),
        ("xtoys", _tool("xtoys_emergency_stop", "Немедленно остановить все режимы XToys", {})),
        ("browser", _tool("browser_navigate", "Открыть URL в управляемом браузере", {"url": {"type": "string"}}, ["url"])),
        ("browser", _tool("browser_search_web", "Найти информацию в интернете и открыть результаты", {"query": {"type": "string"}}, ["query"])),
        ("browser", _tool("browser_search_images", "Открыть поиск изображений по запросу", {"query": {"type": "string"}}, ["query"])),
        ("browser", _tool("browser_extract_text", "Прочитать текст активной веб-страницы", {"max_chars": {"type": "integer", "minimum": 100, "maximum": 10000}})),
        ("browser", _tool("browser_current_tab", "Получить адрес и заголовок активной вкладки", {})),
        ("vision", _tool("vision_analyze_screen", "Описать содержимое активной вкладки с помощью Vision", {"prompt": {"type": "string"}})),
        ("vision", _tool("vision_analyze_desktop", "Описать видимый рабочий стол Windows", {"prompt": {"type": "string"}})),
    ]
    if enabled_capabilities is None:
        return [definition for _, definition in definitions]
    return [definition for capability, definition in definitions if capability in enabled_capabilities]


def get_tool_schemas(enabled_capabilities: set[str] | None = None) -> list[dict[str, Any]]:
    return get_all_tool_definitions(enabled_capabilities)
