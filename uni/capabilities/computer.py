"""Computer Capability - PyAutoGUI + Windows UI Automation"""

import asyncio
import platform
from pathlib import Path
from typing import Any
from PIL import Image

import pyautogui
from ..capabilities.registry import Capability, ToolSchema

# Windows UI Automation
if platform.system() == "Windows":
    try:
        import comtypes
        from comtypes.client import CreateObject
        UIA_AVAILABLE = True
    except ImportError:
        UIA_AVAILABLE = False
else:
    UIA_AVAILABLE = False


class ComputerCapability(Capability):
    def __init__(self, use_uia: bool = True, failsafe: bool = True):
        super().__init__("computer")
        self.use_uia = use_uia and UIA_AVAILABLE
        self.failsafe = failsafe
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0.1

        # Screen dimensions
        self.screen_width, self.screen_height = pyautogui.size()

        self.register_tool(ToolSchema(
            name="click",
            description="Click at screen coordinates",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "clicks": {"type": "integer", "default": 1},
                },
                "required": ["x", "y"],
            },
        ))
        self.register_tool(ToolSchema(
            name="type",
            description="Type text at current cursor position",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "interval": {"type": "number", "default": 0.05, "description": "Delay between keystrokes"},
                },
                "required": ["text"],
            },
        ))
        self.register_tool(ToolSchema(
            name="press",
            description="Press key or key combination",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name (e.g., 'enter', 'ctrl+c', 'alt+tab')"},
                },
                "required": ["key"],
            },
        ))
        self.register_tool(ToolSchema(
            name="move",
            description="Move mouse to coordinates",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number", "default": 0.2},
                },
                "required": ["x", "y"],
            },
        ))
        self.register_tool(ToolSchema(
            name="scroll",
            description="Scroll mouse wheel",
            parameters={
                "type": "object",
                "properties": {
                    "clicks": {"type": "integer", "description": "Positive = up, negative = down"},
                    "x": {"type": "integer", "description": "X coordinate (optional)"},
                    "y": {"type": "integer", "description": "Y coordinate (optional)"},
                },
                "required": ["clicks"],
            },
        ))
        self.register_tool(ToolSchema(
            name="screenshot_region",
            description="Capture screen region",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "default": 0},
                    "y": {"type": "integer", "default": 0},
                    "width": {"type": "integer", "description": "Width (default: full screen)"},
                    "height": {"type": "integer", "description": "Height (default: full screen)"},
                    "save_path": {"type": "string", "description": "Optional path to save"},
                },
            },
        ))
        self.register_tool(ToolSchema(
            name="focus_window",
            description="Focus window by title substring",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title substring"},
                },
                "required": ["title"],
            },
        ))
        self.register_tool(ToolSchema(
            name="get_window_list",
            description="List all visible windows",
            parameters={"type": "object", "properties": {}},
        ))

    async def execute(self, tool_name: str, args: dict) -> Any:
        method = getattr(self, f"_tool_{tool_name}", None)
        if not method:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await method(args)

    # Tool implementations
    async def _tool_click(self, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: pyautogui.click(
            x=args["x"], y=args["y"],
            button=args.get("button", "left"),
            clicks=args.get("clicks", 1)
        ))
        return {"success": True}

    async def _tool_type(self, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: pyautogui.write(
            args["text"], interval=args.get("interval", 0.05)
        ))
        return {"success": True}

    async def _tool_press(self, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: pyautogui.press(args["key"]))
        return {"success": True}

    async def _tool_move(self, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: pyautogui.moveTo(
            args["x"], args["y"], duration=args.get("duration", 0.2)
        ))
        return {"success": True}

    async def _tool_scroll(self, args: dict) -> dict:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: pyautogui.scroll(
            args["clicks"], x=args.get("x"), y=args.get("y")
        ))
        return {"success": True}

    async def _tool_screenshot_region(self, args: dict) -> dict:
        x = args.get("x", 0)
        y = args.get("y", 0)
        width = args.get("width", self.screen_width - x)
        height = args.get("height", self.screen_height - y)

        loop = asyncio.get_event_loop()
        screenshot = await loop.run_in_executor(None, lambda: pyautogui.screenshot(region=(x, y, width, height)))

        if save_path := args.get("save_path"):
            await loop.run_in_executor(None, lambda: screenshot.save(save_path))

        # Convert to base64 for vision
        import base64
        from io import BytesIO
        buffer = BytesIO()
        screenshot.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            "success": True,
            "image_base64": img_base64,
            "width": width,
            "height": height,
        }

    async def _tool_focus_window(self, args: dict) -> dict:
        if not self.use_uia:
            return {"success": False, "error": "UI Automation not available"}

        title = args["title"]
        try:
            import comtypes
            from comtypes.client import CreateObject

            automation = CreateObject("UIAutomationClient.CUIAutomation")
            desktop = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(30005, title)  # NameProperty

            def find_window():
                return desktop.FindFirst(1, condition)  # TreeScope_Children

            element = await asyncio.get_event_loop().run_in_executor(None, find_window)
            if element:
                pattern = element.GetCurrentPattern(10001)  # WindowPattern
                if pattern:
                    pattern.SetWindowVisualState(2)  # Maximized/Normal
                    return {"success": True}
            return {"success": False, "error": "Window not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_get_window_list(self, args: dict) -> dict:
        if not self.use_uia:
            return {"success": False, "error": "UI Automation not available"}

        try:
            import comtypes
            from comtypes.client import CreateObject

            automation = CreateObject("UIAutomationClient.CUIAutomation")
            desktop = automation.GetRootElement()
            condition = automation.CreateTrueCondition()

            def enum_windows():
                results = []
                walker = automation.CreateTreeWalker(condition)
                element = walker.GetFirstChildElement(desktop)
                while element:
                    try:
                        name = element.CurrentName
                        if name:
                            results.append(name)
                    except:
                        pass
                    element = walker.GetNextSiblingElement(element)
                return results

            windows = await asyncio.get_event_loop().run_in_executor(None, enum_windows)
            return {"success": True, "windows": windows}
        except Exception as e:
            return {"success": False, "error": str(e)}