from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from uni.contracts import ToolResult


@dataclass
class VisibleTarget:
    """A target located via UIA with screen coordinates."""
    name: str
    role: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0


class VisibleDesktopDriver:
    """Performs physical input through visible, human-like motion.

    Pipeline: fresh UIA target -> bbox -> human mouse movement -> badge -> click/type.
    All physical actions go through this driver in VISIBLE mode.
    """

    def __init__(self, computer: Any, *, badge_enabled: bool = True) -> None:
        self.computer = computer
        self.badge_enabled = badge_enabled

    async def click(self, target: VisibleTarget, *, button: str = "left") -> ToolResult:
        """Move mouse to target center and click with human-like motion."""
        x = round(target.x + target.width / 2)
        y = round(target.y + target.height / 2)
        try:
            result = await self.computer.execute("click_human", x=x, y=y, button=button)
            return result
        except Exception as exc:
            return ToolResult(success=False, message=f"visible click failed: {exc}")

    async def fill(self, target: VisibleTarget, text: str, *,
                   focus_guard: Callable[[], Awaitable[bool]] | None = None) -> ToolResult:
        """Click to focus, select all, then type or paste text."""
        focus = await self.click(target)
        if not focus.success:
            return focus
        if focus_guard is None or not await focus_guard():
            return ToolResult(success=False, message="keyboard_focus_not_verified")
        try:
            # Select existing text
            sel = await self.computer.execute("press", key="ctrl+a")
            if not sel.success:
                return sel
            if not await focus_guard():
                return ToolResult(success=False, message="keyboard_focus_changed")
            # Type short text; paste long text for speed
            if len(text) < 100:
                return await self.computer.execute("type_unicode", text=text)
            paste = await self.computer.execute("paste", text=text)
            return paste
        except Exception as exc:
            return ToolResult(success=False, message=f"visible fill failed: {exc}")

    async def press(self, key: str) -> ToolResult:
        """Press a key or hotkey."""
        try:
            return await self.computer.execute("press", key=key)
        except Exception as exc:
            return ToolResult(success=False, message=f"visible press failed: {exc}")

    async def focus(self, target: VisibleTarget) -> ToolResult:
        """Click to focus a target without further input."""
        return await self.click(target)
