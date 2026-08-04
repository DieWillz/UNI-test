import asyncio
import subprocess
import pyautogui
from uni.contracts import ToolResult
from .base import Capability

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

class ComputerCapability(Capability):
    name = "computer"
    description = "Управление мышью, клавиатурой, приложениями"

    def __init__(self, use_uia: bool = True, failsafe: bool = True):
        self.use_uia = use_uia
        pyautogui.FAILSAFE = failsafe

    async def launch_app(self, app_name: str) -> ToolResult:
        apps = {
            "notepad": "notepad.exe",
            "блокнот": "notepad.exe",
            "calc": "calc.exe",
            "калькулятор": "calc.exe",
            "explorer": "explorer.exe",
            "проводник": "explorer.exe",
            "chrome": "chrome.exe",
            "браузер": "chrome.exe",
        }
        cmd = apps.get(app_name.lower(), app_name)
        try:
            await asyncio.to_thread(subprocess.Popen, cmd)
            return ToolResult(success=True, message=f"Запущено: {app_name}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def click(self, x: int, y: int, button: str = "left") -> ToolResult:
        try:
            await asyncio.to_thread(pyautogui.click, x, y, button=button)
            return ToolResult(success=True, message=f"Клик ({x},{y})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def type_text(self, text: str, interval: float = 0.05) -> ToolResult:
        try:
            await asyncio.to_thread(pyautogui.typewrite, text, interval=interval)
            return ToolResult(success=True, message=f"Напечатано: {text[:50]}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def press_key(self, key: str) -> ToolResult:
        try:
            await asyncio.to_thread(pyautogui.hotkey, *key.split("+"))
            return ToolResult(success=True, message=f"Нажато: {key}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "launch":
            return await self.launch_app(kwargs.get("app", ""))
        elif action == "click":
            return await self.click(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("button", "left"))
        elif action == "type":
            return await self.type_text(kwargs.get("text", ""), kwargs.get("interval", 0.05))
        elif action == "press":
            return await self.press_key(kwargs.get("key", ""))
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
