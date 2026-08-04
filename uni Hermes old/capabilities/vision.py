from __future__ import annotations

import base64
import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageGrab
from pydantic import BaseModel, Field, ValidationError

from uni.brain import Brain
from uni.browser_session import BrowserSession
from uni.config import Config
from uni.contracts import ToolResult
from .base import Capability

logger = logging.getLogger(__name__)


class ElementLocation(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


def parse_spatial_location(value: Any, image_size: tuple[int, int]) -> ElementLocation:
    """Accept canonical JSON or Moondream normalized spatial references."""
    if isinstance(value, dict):
        return ElementLocation.model_validate(value)
    if not isinstance(value, list) or len(value) not in {2, 4}:
        raise ValueError("Expected a location object or a normalized point/box")
    if not all(isinstance(number, (int, float)) for number in value):
        raise ValueError("Spatial coordinates must be numbers")
    if not all(0 <= float(number) <= 1 for number in value):
        raise ValueError("Normalized spatial coordinates must be between 0 and 1")

    image_width, image_height = image_size
    if len(value) == 2:
        x, y = (float(number) for number in value)
        return ElementLocation(
            x=x * image_width,
            y=y * image_height,
            width=1,
            height=1,
            confidence=0.75,
        )

    x_min, y_min, x_max, y_max = (float(number) for number in value)
    width_ratio, height_ratio = x_max - x_min, y_max - y_min
    if width_ratio <= 0 or height_ratio <= 0:
        raise ValueError("Spatial box has no clickable area")
    area_ratio = width_ratio * height_ratio
    if area_ratio > 0.12 or width_ratio > 0.70 or height_ratio > 0.30:
        raise ValueError("Spatial box is too broad for a safe click")
    return ElementLocation(
        x=x_min * image_width,
        y=y_min * image_height,
        width=width_ratio * image_width,
        height=height_ratio * image_height,
        confidence=0.70,
    )


def extract_json_value(response: str) -> Any:
    text = response.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if text.lower().startswith("null"):
            start = 0
        elif start_candidates:
            start = min(start_candidates)
        else:
            raise ValueError("JSON value not found")
        text = text[start:]
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(text)
    if text[end:].strip():
        raise ValueError("Unexpected text after JSON value")
    return value


class VisionCapability(Capability):
    name = "vision"
    description = "Анализ активной вкладки через локальную VLM"

    def __init__(self, brain: Brain, config: Config, session: BrowserSession):
        self.brain = brain
        self.config = config
        self.session = session
        self.save_dir = Path("screenshots")
        self.save_dir.mkdir(exist_ok=True)
        self._gradio_client: Any = None
        self._gradio_lock = asyncio.Lock()

    @staticmethod
    def _is_missing_endpoint_error(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = ("api_name", "endpoint", "not found", "404", "cannot find a function")
        return any(marker in message for marker in markers)

    def _gradio_predict(self, image: Image.Image, prompt: str) -> str:
        from gradio_client import Client, handle_file

        if self._gradio_client is None:
            self._gradio_client = Client(
                self.config.capabilities.vision.gradio_url,
                verbose=False,
            )
        path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="uni-vision-", suffix=".png", delete=False) as temp:
                path = temp.name
            image.save(path, format="PNG")
            primary = self.config.capabilities.vision.gradio_api_name
            fallback = self.config.capabilities.vision.gradio_fallback_api_name
            try:
                result = self._gradio_client.predict(
                    img=handle_file(path),
                    prompt=prompt,
                    api_name=primary,
                )
            except Exception as exc:
                if not fallback or fallback == primary or not self._is_missing_endpoint_error(exc):
                    raise
                result = self._gradio_client.predict(
                    img=handle_file(path),
                    prompt=prompt,
                    api_name=fallback,
                )
            return str(result)
        finally:
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    async def _ask(self, image: Image.Image, prompt: str, *, preserve_prompt: bool = False) -> str:
        provider = self.config.capabilities.vision.provider.lower()
        if provider == "gradio":
            if not preserve_prompt and re.search(r"[а-яё]", prompt, flags=re.IGNORECASE):
                prompt = (
                    "Describe this browser screenshot. Identify the website, visible controls, "
                    "main text, current state, and any warning. Be concise and factual."
                )
            async with self._gradio_lock:
                return await asyncio.to_thread(self._gradio_predict, image.copy(), prompt)
        if provider == "openai":
            return await self.brain.vision(self._data_url(image), prompt)
        raise ValueError(f"Неизвестный Vision provider: {provider}")

    async def _capture(self) -> tuple[Image.Image, tuple[int, int], str | None]:
        page = await self.session.active_page()
        raw = await page.screenshot(full_page=False)
        image = Image.open(BytesIO(raw)).convert("RGB")
        original_size = image.size
        resize_w = self.config.capabilities.vision.resize_width
        resize_h = self.config.capabilities.vision.resize_height
        if resize_w and resize_h:
            image.thumbnail((resize_w, resize_h), Image.Resampling.LANCZOS)
        save_path = None
        if self.config.capabilities.vision.save_screenshots:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = self.save_dir / f"browser_{timestamp}.png"
            image.save(path, "PNG")
            save_path = str(path)
        return image, original_size, save_path

    async def _capture_desktop(self) -> tuple[Image.Image, tuple[int, int]]:
        image = await asyncio.to_thread(ImageGrab.grab)
        image = image.convert("RGB")
        original_size = image.size
        resize_w = self.config.capabilities.vision.resize_width
        resize_h = self.config.capabilities.vision.resize_height
        if resize_w and resize_h:
            image.thumbnail((resize_w, resize_h), Image.Resampling.LANCZOS)
        return image, original_size

    @staticmethod
    def _data_url(image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    async def analyze_screen(self, prompt: str = "Что находится на активной вкладке?") -> ToolResult:
        if not self.config.capabilities.vision.enabled:
            return ToolResult(success=False, message="Vision отключён в config.yaml")
        try:
            image, _, save_path = await self._capture()
            response = await self._ask(image, prompt)
            data: dict[str, Any] = {"analysis": response}
            if save_path:
                data["screenshot"] = save_path
            return ToolResult(success=True, data=data, message="Активная вкладка проанализирована")
        except Exception as exc:
            logger.warning("Vision analysis unavailable: %s", exc)
            return ToolResult(success=False, message=f"Vision недоступен: {exc}")

    async def find_element(self, description: str) -> ToolResult:
        if not description.strip():
            return ToolResult(success=False, message="Описание элемента пусто")
        try:
            image, original_size, _ = await self._capture()
            analyzed_size = image.size
            prompt = (
                f"Найди элемент: {description!r}. Верни только JSON "
                '{"x": number, "y": number, "width": number, "height": number, "confidence": 0..1} '
                "в координатах изображения или null, если элемента нет."
            )
            response = await self._ask(image, prompt, preserve_prompt=True)
            parsed = extract_json_value(response)
            if parsed is None:
                return ToolResult(success=False, message=f"Элемент «{description}» не найден")
            location = parse_spatial_location(parsed, analyzed_size)
            if location.x + location.width > analyzed_size[0] or location.y + location.height > analyzed_size[1]:
                return ToolResult(success=False, message="VLM вернула координаты за пределами изображения")
            scale_x = original_size[0] / analyzed_size[0]
            scale_y = original_size[1] / analyzed_size[1]
            data = location.model_dump()
            data.update(
                x=round(location.x * scale_x, 2),
                y=round(location.y * scale_y, 2),
                width=round(location.width * scale_x, 2),
                height=round(location.height * scale_y, 2),
            )
            return ToolResult(success=True, data=data, message=f"Элемент «{description}» найден")
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Invalid VLM element response: %s", exc)
            return ToolResult(success=False, message=f"Некорректный ответ Vision: {exc}")
        except Exception as exc:
            logger.exception("Vision element detection failed")
            return ToolResult(success=False, message=f"Ошибка Vision: {exc}")

    async def analyze_desktop(self, prompt: str = "Describe the visible Windows desktop and active application.") -> ToolResult:
        if not self.config.capabilities.vision.enabled:
            return ToolResult(success=False, message="Vision отключён в config.yaml")
        try:
            image, _ = await self._capture_desktop()
            response = await self._ask(image, prompt, preserve_prompt=True)
            return ToolResult(success=True, data={"analysis": response}, message="Рабочий стол проанализирован")
        except Exception as exc:
            logger.warning("Desktop Vision unavailable: %s", exc)
            return ToolResult(success=False, message=f"Desktop Vision недоступен: {exc}")

    async def analyze_file(self, path: str, prompt: str) -> ToolResult:
        if not self.config.capabilities.vision.enabled:
            return ToolResult(success=False, message="Vision отключён в config.yaml")
        try:
            source = Path(path).resolve()
            if not source.is_file():
                return ToolResult(success=False, message="Файл изображения не найден")
            with Image.open(source) as opened:
                image = opened.convert("RGB")
            resize_w = self.config.capabilities.vision.resize_width
            resize_h = self.config.capabilities.vision.resize_height
            if resize_w and resize_h:
                image.thumbnail((resize_w, resize_h), Image.Resampling.LANCZOS)
            response = await self._ask(image, prompt, preserve_prompt=True)
            return ToolResult(
                success=True,
                data={"analysis": response, "path": str(source)},
                message="Кадр камеры проанализирован",
            )
        except Exception as exc:
            logger.warning("Image-file Vision unavailable: %s", exc)
            return ToolResult(success=False, message=f"Vision не смог проанализировать кадр: {exc}")

    async def observe_desktop(self) -> ToolResult:
        try:
            image, original_size = await self._capture_desktop()
            return ToolResult(
                success=True,
                data={"width": original_size[0], "height": original_size[1], "captured": True},
                message="Получен свежий снимок рабочего стола",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка снимка рабочего стола: {exc}")

    async def find_desktop_element(self, description: str) -> ToolResult:
        if not description.strip():
            return ToolResult(success=False, message="Описание элемента пусто")
        try:
            image, original_size = await self._capture_desktop()
            analyzed_size = image.size
            prompt = (
                "Locate exactly one visible Windows UI element described below. The label may use Cyrillic. "
                f"Target: {description!r}. Return only JSON "
                '{"x": number, "y": number, "width": number, "height": number, "confidence": 0..1} '
                "in screenshot coordinates, or null when the target is not clearly visible."
            )
            response = await self._ask(image, prompt, preserve_prompt=True)
            parsed = extract_json_value(response)
            if parsed is None:
                return ToolResult(success=False, message=f"Элемент «{description}» не найден")
            location = parse_spatial_location(parsed, analyzed_size)
            if location.confidence < 0.55:
                return ToolResult(success=False, message=f"Низкая уверенность Vision: {location.confidence:.2f}")
            if location.x + location.width > analyzed_size[0] or location.y + location.height > analyzed_size[1]:
                return ToolResult(success=False, message="VLM вернула координаты за пределами рабочего стола")
            scale_x = original_size[0] / analyzed_size[0]
            scale_y = original_size[1] / analyzed_size[1]
            data = location.model_dump()
            data.update(
                x=round(location.x * scale_x, 2),
                y=round(location.y * scale_y, 2),
                width=round(location.width * scale_x, 2),
                height=round(location.height * scale_y, 2),
            )
            return ToolResult(success=True, data=data, message=f"Элемент «{description}» найден на рабочем столе")
        except (ValueError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Invalid desktop VLM element response: %s", exc)
            return ToolResult(success=False, message=f"Некорректный ответ Desktop Vision: {exc}")
        except Exception as exc:
            logger.exception("Desktop Vision element detection failed")
            return ToolResult(success=False, message=f"Ошибка Desktop Vision: {exc}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "analyze_screen":
            return await self.analyze_screen(str(kwargs.get("prompt", "Что находится на активной вкладке?")))
        if action == "find_element":
            return await self.find_element(str(kwargs.get("description", "")))
        if action == "analyze_desktop":
            return await self.analyze_desktop(str(kwargs.get("prompt", "Describe the visible Windows desktop.")))
        if action == "observe_desktop":
            return await self.observe_desktop()
        if action == "find_desktop_element":
            return await self.find_desktop_element(str(kwargs.get("description", "")))
        if action == "analyze_file":
            return await self.analyze_file(
                str(kwargs.get("path", "")),
                str(kwargs.get("prompt", "Describe this camera frame factually.")),
            )
        return ToolResult(success=False, message=f"Неизвестное действие vision.{action}")
