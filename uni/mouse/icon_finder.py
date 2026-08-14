"""Поиск иконок на экране через ВНЕШНИЙ Moondream2-endpoint (HTTP).

Hermes, 2026-08-14. Принцип (исправление нерабочего из директивы):
- Директива предлагала попиксельное сканирование (step=30, вызов VLM на каждый
  кусок) -> сотни вызовов на один поиск. Это неработоспособно.
- Вместо этого: ОДИН скриншот всего экрана (ImageGrab) + ОДИН запрос к
  Moondream-endpoint с вопросом "где находится <иконка>, верни bbox xyxy".
- Модель уже запущена отдельно (Pinokio/imageGram) -> грузим ТОЛЬКО по HTTP,
  не в процесс Юни.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import urllib.request

from PIL import Image, ImageGrab

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except Exception:  # pragma: no cover - cv2 опционален для поиска
    _HAS_CV2 = False


@dataclass
class IconMatch:
    position: tuple[int, int]          # центр иконки (x, y)
    region: tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    description: str


# 🤖 Список кандидатов на endpoint Moondream (Pinokio/imageGram/Gradio).
# Реальный адрес берётся из config.vision.moondream_url; это fallback-скан.
_MOONDREAM_CANDIDATES = [
    "http://127.0.0.1:7860",   # типичный Gradio/Pinokio
    "http://127.0.0.1:7861",
    "http://127.0.0.1:1234",   # LM Studio-стиль
    "http://localhost:7860",
]


class IconFinder:
    """Поиск иконок по описанию через внешний VLM (без загрузки модели в Юни)."""

    def __init__(self, endpoint: Optional[str] = None, *, timeout: float = 20.0) -> None:
        self.endpoint = endpoint  # если None -> берётся из config при первом вызове
        self.timeout = timeout
        self._resolved: Optional[str] = None
        self._last_capture = 0.0
        self._min_interval = 0.3

    # ---- endpoint resolution -------------------------------------------------
    def _resolve_endpoint(self) -> str:
        if self._resolved:
            return self._resolved
        # 1) явный
        if self.endpoint:
            self._resolved = self.endpoint.rstrip("/")
            return self._resolved
        # 2) из config (если доступен)
        try:
            from uni.config import load_config
            cfg = load_config().vision
            url = getattr(cfg, "moondream_url", None) or getattr(cfg, "gradio_url", None)
            if url:
                self._resolved = str(url).rstrip("/")
                return self._resolved
        except Exception:
            pass
        # 3) автодетект (быстрый TCP-проброс по кандидатам)
        self._resolved = self._autodetect()
        return self._resolved

    def _autodetect(self) -> str:
        import socket
        for cand in _MOONDREAM_CANDIDATES:
            try:
                host, port = cand.replace("http://", "").split(":")
                with socket.create_connection((host, int(port)), timeout=0.4):
                    return cand
            except Exception:
                continue
        return _MOONDREAM_CANDIDATES[0]  # последняя надежда (call потом упадёт понятно)

    # ---- screen capture ------------------------------------------------------
    def capture_screen(self, region: Optional[tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
        now = time.time()
        if now - self._last_capture < self._min_interval:
            return None
        try:
            if region:
                x, y, w, h = region
                shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            else:
                shot = ImageGrab.grab()
            self._last_capture = now
            return shot
        except Exception:
            return None

    # ---- HTTP to Moondream ---------------------------------------------------
    def _query_vlm(self, image_b64: str, prompt: str) -> Optional[str]:
        endpoint = self._resolve_endpoint()
        # Gradio-совместимый вызов /api/predict или /predict; пробуем оба.
        payload = {"data": [prompt, image_b64]}
        last_err: Optional[str] = None
        for path in ("/api/predict", "/predict"):
            url = endpoint + path
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read().decode("utf-8", "replace")
                return self._parse_response(raw)
            except Exception as exc:  # пробуем следующий путь
                last_err = f"{path}: {exc}"
                continue
        # Если ни один путь не сработал — вернём None, логируем в вызывающем
        self._last_err = last_err
        return None

    def _parse_response(self, raw: str) -> Optional[str]:
        try:
            data = json.loads(raw)
            # Gradio часто возвращает {"data": [text, ...]}
            if isinstance(data, dict) and "data" in data:
                val = data["data"]
                if isinstance(val, list) and val:
                    return str(val[0])
                return str(val)
            return raw
        except Exception:
            return raw

    # ---- public API ----------------------------------------------------------
    def find_icon(self, target_description: str, region: Optional[tuple[int, int, int, int]] = None,
                  threshold: float = 0.5) -> Optional[IconMatch]:
        """Найти иконку по описанию. ОДИН скриншот + ОДИН запрос к VLM."""
        shot = self.capture_screen(region)
        if shot is None:
            return None
        try:
            buf = io.BytesIO()
            shot.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

        w, h = shot.size
        prompt = (
            f"На этом скриншоте найди элемент: «{target_description}». "
            f"Верни ТОЛЬКО JSON вида {{\"found\": true/false, \"x\": <центр X>, "
            f"\"y\": <центр Y>, \"w\": <ширина>, \"h\": <высота>, \"conf\": <0..1>}}. "
            f"Координаты — в пикселях относительно левого верхнего угла (ширина {w}, высота {h}). "
            f"Если не уверен — found:false."
        )
        text = self._query_vlm(b64, prompt)
        if not text:
            return None
        try:
            j = json.loads(self._extract_json(text))
        except Exception:
            return None
        if not j.get("found"):
            return None
        cx, cy = int(j.get("x", 0)), int(j.get("y", 0))
        iw, ih = int(j.get("w", 0)), int(j.get("h", 0))
        conf = float(j.get("conf", 0.0))
        if conf < threshold:
            return None
        # region в абсолютных координатах, если задан region
        if region:
            ox, oy, _, _ = region
            cx += ox
            cy += oy
        return IconMatch(
            position=(cx, cy),
            region=(cx - iw // 2, cy - ih // 2, iw, ih),
            confidence=conf,
            description=target_description,
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        if "{" in text and "}" in text:
            a, b = text.find("{"), text.rfind("}")
            return text[a:b + 1]
        return text

    def find_all_icons(self, descriptions: list[str], region=None, **kw) -> list[IconMatch]:
        out: list[IconMatch] = []
        for d in descriptions:
            m = self.find_icon(d, region=region, **kw)
            if m:
                out.append(m)
        return out
