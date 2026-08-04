import base64
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageGrab
from uni.brain import Brain
from uni.config import Config
from uni.contracts import ToolResult
from .base import Capability

class VisionCapability(Capability):
    name = "vision"
    description = "Анализ экрана через VLM"

    def __init__(self, brain: Brain, config: Config):
        self.brain = brain
        self.config = config
        self.save_dir = Path("screenshots")
        self.save_dir.mkdir(exist_ok=True)

    async def analyze_screen(self, prompt: str = "Что на экране?") -> ToolResult:
        try:
            img = ImageGrab.grab()
            resize_w = getattr(self.config.capabilities.vision, 'resize_width', 320)
            resize_h = getattr(self.config.capabilities.vision, 'resize_height', 240)
            if resize_w and resize_h:
                img.thumbnail((resize_w, resize_h), Image.Resampling.LANCZOS)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            data_url = f"data:image/png;base64,{b64}"
            if getattr(self.config.capabilities.vision, 'save_screenshots', False):
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                fname = self.save_dir / f"screenshot_{ts}.png"
                img.save(fname, "PNG")
                save_path = str(fname)
            else:
                save_path = None
            response = await self.brain.vision(data_url, prompt)
            result = ToolResult(success=True, data=response, message="Screen analyzed")
            if save_path:
                result.data = {"analysis": response, "screenshot": save_path}
            return result
        except Exception as e:
            return ToolResult(success=False, message=f"Vision error: {e}")

    async def find_element(self, description: str) -> ToolResult:
        try:
            img = ImageGrab.grab()
            resize_w = getattr(self.config.capabilities.vision, 'resize_width', 320)
            resize_h = getattr(self.config.capabilities.vision, 'resize_height', 240)
            if resize_w and resize_h:
                img.thumbnail((resize_w, resize_h), Image.Resampling.LANCZOS)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            data_url = f"data:image/png;base64,{b64}"
            prompt = f"Найди на изображении элемент: '{description}'. Верни JSON с полями x, y, width, height, confidence. Если не найден, верни null."
            response = await self.brain.vision(data_url, prompt)
            try:
                data = json.loads(response)
                if data is None:
                    return ToolResult(success=False, message=f"Элемент '{description}' не найден")
                return ToolResult(success=True, data=data, message=f"Найден '{description}'")
            except:
                return ToolResult(success=False, message=f"Ошибка парсинга: {response[:100]}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "analyze_screen":
            return await self.analyze_screen(kwargs.get("prompt", "Что на экране?"))
        elif action == "find_element":
            return await self.find_element(kwargs.get("description", ""))
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
