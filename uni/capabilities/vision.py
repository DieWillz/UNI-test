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
from uni.utils.file_lock import acquire_lock, release_lock

logger = logging.getLogger(__name__)

# 🤖 FIX-AUDIT A-02: ЕДИНСТВЕННЫЙ источник истины для порога уверенности локации.
# vision.py решает ТОЛЬКО за себя: при conf < порога возвращает success=False,
# но с data (confidence доступен оркестратору). Решение clarify/повтор —
# за visual_action. Слои согласованы через эту константу.
VISION_CONFIDENCE_THRESHOLD = 0.55


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
            if preserve_prompt:
                # Keep the caller's prompt (e.g. a JSON-instruction) but force
                # the model to answer in Russian.
                prompt = f"{prompt}\nОтвечай только по-русски."
            else:
                prompt = (
                    "Кратко опиши этот снимок экрана по-русски. Назови сайт, видимые "
                    "элементы управления, основной текст, текущее состояние и любые "
                    "предупреждения. Будь лаконичен и фактичен."
                )
            async with self._gradio_lock:
                return await asyncio.to_thread(self._gradio_predict, image.copy(), prompt)
        if provider in ("auto", "openai"):
            return await self.brain.vision(self._data_url(image), f"{prompt}\nОтвечай только по-русски.")
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

    async def analyze_desktop(self, prompt: str = "Кратко опиши видимый рабочий стол Windows и активное приложение по-русски.") -> ToolResult:
        if not self.config.capabilities.vision.enabled:
            return ToolResult(success=False, message="Vision отключён в config.yaml")
        try:
            image, _ = await self._capture_desktop()
            response = await self._ask(image, prompt, preserve_prompt=True)
            return ToolResult(success=True, data={"analysis": response}, message="Рабочий стол проанализирован")
        except Exception as exc:
            logger.warning("Desktop Vision unavailable: %s", exc)
            # 🤖 локальный fallback (UIA-describe), если VLM упала и включён флаг
            if self.config.capabilities.vision.local_fallback_enabled:
                try:
                    from uni.tools.local_vision_fallback import uia_describe
                    local = uia_describe()
                    if local:
                        return ToolResult(success=True, data={"analysis": local},
                                          message="Рабочий стол проанализирован локально (UIA)")
                except Exception as fexc:
                    logger.debug("local UIA describe не сработал: %s", fexc)
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
        # 🤖 V-02 (2026-08-13): порядок БЕЗ модели сначала — Tier-0 каскад
        # (UIA -> OCR -> DOM). Только если Tier-0 пустой — идём в Tier-2 (VLM).
        # Это «лёгкое зрение»: базовые клики (Пуск, кнопка) без VLM.
        try:
            from uni.tools.local_vision_fallback import find_desktop_element_tier0
            local = find_desktop_element_tier0(description)
            if local:
                local = dict(local)
                src = local.get("source", "uia")
                return ToolResult(
                    success=True, data=local,
                    message=f"Элемент «{description}» найден локально (Tier-0: {src})",
                )
        except Exception as exc:
            logger.debug("Tier-0 поиск пропущен: %s", exc)
        # Tier-2: VLM (как раньше).
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
            if location.confidence < VISION_CONFIDENCE_THRESHOLD:
                # 🤖 FIX-AUDIT A-02: НЕ решаем за оркестратора. Возвращаем
                # success=False, НО с data (confidence доступна), чтобы
                # visual_action могла принять решение clarify/повтор.
                # Контракт success=False сохранён (другие потребители не ломаются).
                scale_x = original_size[0] / analyzed_size[0]
                scale_y = original_size[1] / analyzed_size[1]
                data = location.model_dump()
                data.update(
                    x=round(location.x * scale_x, 2),
                    y=round(location.y * scale_y, 2),
                    width=round(location.width * scale_x, 2),
                    height=round(location.height * scale_y, 2),
                    low_confidence=True,
                )
                return ToolResult(
                    success=False,
                    data=data,
                    message=f"Низкая уверенность Vision: {location.confidence:.2f}",
                )
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
            # 🤖 локальный fallback (UIA), если VLM упала и включён флаг
            if self.config.capabilities.vision.local_fallback_enabled:
                try:
                    from uni.tools.local_vision_fallback import uia_find_element
                    local = uia_find_element(description)
                    if local is not None:
                        return ToolResult(success=True, data=local,
                                          message=f"Элемент «{description}» найден локально (UIA)")
                except Exception as fexc:
                    logger.debug("local UIA fallback не сработал: %s", fexc)
            return ToolResult(success=False, message=f"Ошибка Desktop Vision: {exc}")

    async def capture_screen_png(self, label: str = "cva") -> ToolResult:
        """Снимок рабочего стола -> runtime/screenshots/<label>_<ts>.png (с lock)."""
        try:
            image, _ = await self._capture_desktop()
            out_dir = Path(__file__).resolve().parents[2] / "runtime" / "screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = out_dir / f"{label}_{ts}.png"
            if acquire_lock(str(path)):
                try:
                    image.save(path)
                finally:
                    release_lock(str(path))
            else:
                image.save(path)
            return ToolResult(success=True, data={"path": str(path)}, message=f"Снимок: {path}")
        except Exception as exc:
            return ToolResult(success=False, message=f"capture_screen_png ошибка: {exc}")

    def compare_screenshots(self, path1: str, path2: str, threshold: float = 0.95) -> bool:
        """Сравнение двух PNG через OpenCV (matchTemplate). similarity>threshold."""
        try:
            import cv2
            import numpy as np
            img1 = cv2.imread(path1)
            img2 = cv2.imread(path2)
            if img1 is None or img2 is None:
                return False
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            res = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
            return float(np.max(res)) > threshold
        except Exception as exc:
            logger.warning("compare_screenshots ошибка: %s", exc)
            return False

    # 🤖 V-03 (2026-08-13): Tier-1 verify — дифф РЕГИОНА скрина через numpy.
    # Возвращает долю изменившихся пикселей (0..1). Выше threshold -> изменение.
    def region_diff(self, path1: str, path2: str, threshold: float = 0.15) -> float:
        """Доля отличающихся пикселей между двумя PNG (0..1). None при ошибке."""
        try:
            import cv2
            import numpy as np
            a = cv2.imread(path1)
            b = cv2.imread(path2)
            if a is None or b is None:
                return float("nan")
            if a.shape != b.shape:
                b = cv2.resize(b, (a.shape[1], a.shape[0]))
            diff = cv2.absdiff(a, b)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            changed = (gray > 25).mean()
            return float(changed)
        except Exception as exc:
            logger.warning("region_diff ошибка: %s", exc)
            return float("nan")

    # 🤖 V-04 (2026-08-13): Tier-2 (VLM) доступна ли по железу?
    # nvidia-smi -> свободно >= tier2_min_vram_gb ГБ. False при отсутствии GPU/
    # утилиты/недостатке памяти. Честно (без мока): если nvidia-smi нет — False.
    def tier2_gpu_available(self, min_vram_gb: int | None = None) -> tuple[bool, str]:
        min_vram = min_vram_gb or self.config.capabilities.vision.tier2_min_vram_gb
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode != 0:
                return False, "nvidia-smi недоступен (не nvidia GPU или утилита не в PATH)"
            frees = [int(x.strip()) for x in out.stdout.splitlines() if x.strip().isdigit()]
            if not frees:
                return False, "nvidia-smi не вернул данные о памяти"
            best = max(frees)
            if best < min_vram * 1024:
                return False, f"свободно {best} МБ < {min_vram} ГБ (Tier-2 VLM пропускается)"
            return True, f"свободно {best} МБ >= {min_vram} ГБ"
        except FileNotFoundError:
            return False, "nvidia-smi не найден (не nvidia GPU)"
        except Exception as exc:
            return False, f"проверка GPU упала: {exc}"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "analyze_screen":
            return await self.analyze_screen(str(kwargs.get("prompt", "Что находится на активной вкладке?")))
        if action == "find_element":
            return await self.find_element(str(kwargs.get("description", "")))
        if action == "analyze_desktop":
            return await self.analyze_desktop(str(kwargs.get("prompt", "Кратко опиши видимый рабочий стол Windows по-русски.")))
        if action == "observe_desktop":
            return await self.observe_desktop()
        if action == "find_desktop_element":
            return await self.find_desktop_element(str(kwargs.get("description", "")))
        if action == "analyze_file":
            return await self.analyze_file(
                str(kwargs.get("path", "")),
                str(kwargs.get("prompt", "Опиши этот кадр с камеры фактически, по-русски.")),
            )
        if action == "region_diff":
            # 🤖 V-03: дифф региона двух скринов
            p1 = str(kwargs.get("path1", ""))
            p2 = str(kwargs.get("path2", ""))
            if not p1 or not p2:
                return ToolResult(success=False, message="region_diff требует path1 и path2")
            thr = float(kwargs.get("threshold", 0.15))
            d = self.region_diff(p1, p2, thr)
            if d != d:  # nan
                return ToolResult(success=False, message="region_diff не удался (ошибка чтения)")
            return ToolResult(success=True, data={"changed_ratio": d, "changed": d >= thr},
                              message=f"изменено {d:.3f} пикселей (threshold {thr})")
        if action == "tier2_gpu_available":
            # 🤖 V-04: проверка GPU для Tier-2 VLM
            ok, why = self.tier2_gpu_available(int(kwargs["min_vram_gb"]) if kwargs.get("min_vram_gb") else None)
            return ToolResult(success=ok, data={"available": ok, "reason": why},
                              message=why)
        return ToolResult(success=False, message=f"Неизвестное действие vision.{action}")
