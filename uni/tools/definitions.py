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
