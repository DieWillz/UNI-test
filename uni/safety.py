"""SafetyGuard — заглушка: пользователь имеет физический пульт.

Осталась только логика автономии (whitelist инструментов по уровням),
чтобы авто-режим случайно не делал деструктивных действий.
Никаких стоп-слов, лимитов и таймеров.
"""

from __future__ import annotations

from dataclasses import dataclass

AUTONOMY_TOOLS: dict[str, frozenset[str]] = {
    "off": frozenset(),
    "observe": frozenset({"camera_capture", "vision_analyze_screen", "vision_analyze_desktop"}),
    "suggest": frozenset({"camera_capture", "vision_analyze_screen", "vision_analyze_desktop", "speak"}),
    "act": frozenset({
        "xtoys_get_status", "xtoys_set_intensity", "xtoys_select_pattern",
        "mouse_drive", "cursor_label", "speak",
        "camera_capture", "vision_analyze_screen", "vision_analyze_desktop",
        "browser_navigate", "browser_click_selector",
    }),
}


@dataclass(slots=True)
class SafetyConfig:
    autonomy_level: str = "off"  # off | observe | suggest | act


class SafetyGuard:
    def __init__(self, cfg: SafetyConfig) -> None:
        self.cfg = cfg

    @staticmethod
    def contains_safeword(text: str) -> bool:
        return False

    def autonomy_tools(self) -> frozenset[str]:
        return AUTONOMY_TOOLS.get(self.cfg.autonomy_level, frozenset())

    def validate_tool(self, tool: str, args: dict, **kwargs) -> tuple[bool, str]:
        return True, ""

    def start_session(self) -> None: ...
    def end_session(self) -> None: ...
    def session_check(self) -> tuple[bool, str]:
        return True, ""
