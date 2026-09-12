from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from uni.contracts import ToolResult
from uni.operator.action_registry import DEFAULT_ACTION_REGISTRY


class ToolExecutor:
    _control_mode: ContextVar[str] = ContextVar("uni_control_mode", default="auto")
    _MOUSE_ONLY_BLOCKED = frozenset({
        "browser.navigate", "browser.search_web", "browser.search_images",
        "browser.click_selector", "browser.type_selector", "browser.extract_text",
        "browser.screenshot", "browser.save_screenshot", "browser.current_tab",
    })

    def __init__(self, capability_registry, action_registry=DEFAULT_ACTION_REGISTRY):
        self.registry = capability_registry
        self.action_registry = action_registry

    @classmethod
    def canonical_name(cls, tool_name: str) -> str:
        return DEFAULT_ACTION_REGISTRY.canonical_name(tool_name)

    @classmethod
    def set_control_mode(cls, mode: str):
        if mode not in {"auto", "mouse_only"}:
            raise ValueError("bad control mode")
        return cls._control_mode.set(mode)

    @classmethod
    def reset_control_mode(cls, token) -> None:
        cls._control_mode.reset(token)

    @classmethod
    def mouse_only(cls) -> bool:
        return cls._control_mode.get() == "mouse_only"

    @classmethod
    def action_allowed(cls, name: str) -> bool:
        if not cls.mouse_only():
            return True
        name = cls.canonical_name(name)
        return name in {
            "operator.desktop.inspect", "operator.desktop.read", "operator.desktop.click",
            "operator.desktop.fill", "operator.desktop.press", "operator.desktop.focus",
            "computer.focus_app", "computer.click", "computer.click_human",
            "computer.move", "computer.scroll", "computer.press", "computer.type", "computer.paste",
            "computer.list_visible_windows", "computer.inspect_accessible_elements",
            "vision.analyze_desktop", "vision.observe_desktop", "vision.find_desktop_element",
        }

    async def execute(self, tool_name: str, args: dict[str, Any] | None = None) -> ToolResult:
        canonical = self.action_registry.canonical_name(tool_name)
        if not self.action_allowed(canonical):
            return ToolResult(
                success=False,
                message=("tool_blocked_by_mouse_only_mode: разрешены только screen/vision "
                         "и физические mouse/keyboard действия"),
            )
        try:
            spec = self.action_registry.get(canonical)
        except KeyError:
            return ToolResult(success=False, message=f"Неизвестный инструмент: {tool_name}")
        capability = self.registry.get(spec.capability)
        if capability is None:
            return ToolResult(
                success=False,
                message=f"Capability '{spec.capability}' не зарегистрирована",
            )
        try:
            result = await capability.execute(spec.action, **(args or {}))
            if not isinstance(result, ToolResult):
                return ToolResult(success=False, message=f"{canonical} вернул некорректный результат")
            return result
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка {canonical}: {exc}")
