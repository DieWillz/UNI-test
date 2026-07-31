from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from uni.contracts import ToolResult


class VisualUIOperator:
    """Bounded observe-locate-act operator over canonical tools."""

    def __init__(
        self,
        tool_executor,
        *,
        max_steps: int = 8,
        log: Callable[[str, object], None] | None = None,
    ) -> None:
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.log = log or (lambda _event, _message: None)
        self.steps_used = 0

    async def _run(self, action: str, args: dict[str, Any]) -> ToolResult:
        if self.steps_used >= self.max_steps:
            return ToolResult(success=False, message="Достигнут лимит визуальных действий")
        self.steps_used += 1
        self.log("GUI_ACTION", f"{action} {args}")
        result = await self.tool_executor.execute(action, args)
        self.log("GUI_RESULT", f"{action}: {result.message}")
        return result

    async def focus_app(self, app: str) -> ToolResult:
        return await self._run("computer.focus_app", {"app": app})

    async def open_url_in_app(self, app: str, url: str) -> ToolResult:
        focused = await self.focus_app(app)
        if not focused.success:
            return focused
        selected = await self._run("computer.press", {"key": "ctrl+l"})
        if not selected.success:
            return selected
        pasted = await self._run("computer.paste", {"text": url})
        if not pasted.success:
            return pasted
        opened = await self._run("computer.press", {"key": "enter"})
        if not opened.success:
            return opened
        await asyncio.sleep(3.0)
        observed = await self._run("vision.observe_desktop", {})
        if not observed.success:
            return observed
        return ToolResult(success=True, message=f"Открыт адрес {url} в приложении {app}")

    async def read_active_url(self, app: str = "browser") -> ToolResult:
        focused = await self.focus_app(app)
        if not focused.success:
            return focused
        selected = await self._run("computer.press", {"key": "ctrl+l"})
        if not selected.success:
            return selected
        await asyncio.sleep(0.2)
        result = await self._run("computer.read_focused_accessible_text", {})
        await self._run("computer.press", {"key": "esc"})
        if not result.success or not isinstance(result.data, dict):
            return result
        value = str(result.data.get("value", "")).strip()
        if not value:
            return ToolResult(success=False, message="Адресная строка браузера не предоставила URL")
        return ToolResult(success=True, data={"url": value}, message="Адрес активной вкладки прочитан")

    async def click_visible(
        self,
        description: str,
        *,
        accessible_name: str | None = None,
        control_type: str = "",
    ) -> ToolResult:
        located = await self._run("vision.find_desktop_element", {"description": description})
        if (not located.success or not isinstance(located.data, dict)) and accessible_name:
            located = await self._run(
                "computer.find_accessible_element",
                {"name": accessible_name, "control_type": control_type},
            )
        if not located.success or not isinstance(located.data, dict):
            return located
        try:
            x = float(located.data["x"]) + float(located.data["width"]) / 2
            y = float(located.data["y"]) + float(located.data["height"]) / 2
        except (KeyError, TypeError, ValueError):
            return ToolResult(success=False, message="Vision вернула неполные координаты")
        clicked = await self._run("computer.click", {"x": round(x), "y": round(y)})
        if not clicked.success:
            return clicked
        await asyncio.sleep(0.6)
        observed = await self._run("vision.observe_desktop", {})
        if not observed.success:
            return observed
        return ToolResult(success=True, data={"x": x, "y": y}, message=f"Нажат элемент: {description}")

    async def set_vertical_slider(self, description: str, value: int) -> ToolResult:
        bounded = max(0, min(int(value), 100))
        located = await self._run("vision.find_desktop_element", {"description": description})
        if not located.success or not isinstance(located.data, dict):
            return located
        try:
            left = float(located.data["x"])
            top = float(located.data["y"])
            width = float(located.data["width"])
            height = float(located.data["height"])
        except (KeyError, TypeError, ValueError):
            return ToolResult(success=False, message="Vision вернула неполные координаты слайдера")
        if width < 8 or height < 40 or height <= width:
            return ToolResult(success=False, message="Найденная область не похожа на вертикальный слайдер")
        inset = min(3.0, height / 10)
        x = left + width / 2
        y = top + inset + (height - inset * 2) * (1.0 - bounded / 100.0)
        clicked = await self._run("computer.click", {"x": round(x), "y": round(y)})
        if not clicked.success:
            return clicked
        await asyncio.sleep(0.6)
        observed = await self._run("vision.observe_desktop", {})
        if not observed.success:
            return observed
        return ToolResult(
            success=True,
            data={"x": x, "y": y, "requested_percent": bounded, "verified_physical": False},
            message=f"Вертикальный слайдер нажат на уровне {bounded}% и экран повторно снят",
        )

    async def paste_into_visible(
        self,
        field_description: str,
        text: str,
        *,
        accessible_name: str | None = None,
        control_type: str = "",
    ) -> ToolResult:
        focused = await self.click_visible(
            field_description,
            accessible_name=accessible_name,
            control_type=control_type,
        )
        if not focused.success:
            return focused
        pasted = await self._run("computer.paste", {"text": text})
        if not pasted.success:
            return pasted
        await asyncio.sleep(0.4)
        observed = await self._run("vision.observe_desktop", {})
        if not observed.success:
            return observed
        if accessible_name:
            verified = await self._run("computer.read_accessible_value", {"name": accessible_name})
            actual = verified.data.get("value") if verified.success and isinstance(verified.data, dict) else None
            if actual != text:
                repaired = await self._run(
                    "computer.replace_accessible_text",
                    {"name": accessible_name, "text": text},
                )
                if not repaired.success:
                    return ToolResult(success=False, message="Текст не появился в поле после вставки")
                verified = await self._run("computer.read_accessible_value", {"name": accessible_name})
                actual = verified.data.get("value") if verified.success and isinstance(verified.data, dict) else None
                if actual != text:
                    return ToolResult(success=False, message="Черновик не совпадает с заданным текстом")
        return ToolResult(success=True, message="Черновик вставлен и подтверждён в видимом поле")

    @staticmethod
    def _telegram_app(account: str) -> str:
        normalized = account.casefold().strip()
        if normalized in {"uni", "telegram_uni"}:
            return "telegram_uni"
        if normalized in {"user", "telegram_user"}:
            return "telegram_user"
        raise ValueError("Неизвестный Telegram-аккаунт; допустимы uni или user")

    async def draft_telegram_message(
        self,
        contact: str,
        text: str,
        *,
        account: str = "uni",
    ) -> ToolResult:
        try:
            app = self._telegram_app(account)
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))
        focused = await self.focus_app(app)
        if not focused.success:
            return focused
        for target, accessible_name in (
            ("Telegram folder named Личные in the far-left sidebar", "Личные"),
            (f"Telegram chat named {contact} in the chat list", contact),
        ):
            result = await self.click_visible(
                target,
                accessible_name=accessible_name,
                control_type="list_item",
            )
            if not result.success:
                return result
        result = await self.paste_into_visible(
            "Telegram message input field at the bottom of the open chat, with placeholder Сообщение...",
            text,
            accessible_name="Сообщение...",
            control_type="edit",
        )
        if not result.success:
            return result
        return ToolResult(
            success=True,
            data={
                "account": app,
                "contact": contact,
                "draft": text,
                "requires_confirmation": True,
            },
            message=f"Черновик для {contact} подготовлен; отправка ожидает отдельного подтверждения",
        )

    async def send_focused_draft(self, *, account: str = "uni") -> ToolResult:
        try:
            app = self._telegram_app(account)
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))
        focused = await self.focus_app(app)
        if not focused.success:
            return focused
        observed = await self._run("vision.observe_desktop", {})
        if not observed.success:
            return observed
        return await self._run("computer.press", {"key": "enter"})
