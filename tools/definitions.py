from typing import Any, Dict, List

def get_all_tool_definitions() -> List[Dict[str, Any]]:
    return [
        # XToys
        {"type": "function", "function": {"name": "xtoys_toggle", "description": "Включить/выключить устройство в XToys.app", "parameters": {"type": "object", "properties": {"device": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "xtoys_set_intensity", "description": "Установить интенсивность 0-100", "parameters": {"type": "object", "properties": {"device": {"type": "string"}, "value": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["value"]}}},
        {"type": "function", "function": {"name": "xtoys_select_pattern", "description": "Выбрать паттерн: wave, pulse, tease, punish", "parameters": {"type": "object", "properties": {"device": {"type": "string"}, "pattern": {"type": "string", "enum": ["wave", "pulse", "tease", "punish"]}}, "required": ["pattern"]}}},
        {"type": "function", "function": {"name": "xtoys_get_status", "description": "Получить статус устройства", "parameters": {"type": "object", "properties": {"device": {"type": "string"}}, "required": []}}},
        # Browser
        {"type": "function", "function": {"name": "browser_navigate", "description": "Перейти на URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
        {"type": "function", "function": {"name": "browser_click_selector", "description": "Кликнуть по CSS-селектору", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
        {"type": "function", "function": {"name": "browser_type_selector", "description": "Ввести текст в поле", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]}}},
        # Computer
        {"type": "function", "function": {"name": "computer_launch", "description": "Запустить приложение (notepad, calc, chrome)", "parameters": {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]}}},
        {"type": "function", "function": {"name": "computer_click", "description": "Кликнуть по координатам", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
        {"type": "function", "function": {"name": "computer_type", "description": "Напечатать текст", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
        {"type": "function", "function": {"name": "computer_press", "description": "Нажать клавишу", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
        # Speech
        {"type": "function", "function": {"name": "speech_speak", "description": "Озвучить текст", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
        {"type": "function", "function": {"name": "speech_listen", "description": "Распознать речь", "parameters": {"type": "object", "properties": {"duration": {"type": "integer", "default": 5}}}, "required": []}},
        # Vision
        {"type": "function", "function": {"name": "vision_analyze_screen", "description": "Проанализировать экран", "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "default": "Что на экране?"}}, "required": []}}},
    ]
