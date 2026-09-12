"""Smoke-проверка зрения UNI против живого LM Studio (после загрузки VLM).

Запуск (в консоли, где виден LM Studio на :1234):
  cd C:/LLM/UNI
  set PYTHONPATH=C:/LLM/UNI
  C:/LLM/python312/python.exe -m uni.webui.verify_vision

Что проверяет:
  1. Brain поднимается на base_url из config (lmstudio :1234 по умолчанию).
  2. /v1/models отдаёт хотя бы одну загруженную модель.
  3. vision() успешно описывает тестовую картинку (1x1 png), т.е.
     выбранная VLM реально понимает изображения.

Если пункт 3 падает с «does not support images» — значит модель не
multimodal; загрузите в LM Studio VLM (Qwen2.5-VL / Moondream / SmolVLM / ...).
"""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path

from PIL import Image

from uni.brain import Brain
from uni.config import load_config


def _test_png() -> str:
    img = Image.new("RGB", (64, 64), (120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def main() -> int:
    cfg = load_config()
    print(f"[brain] provider={cfg.brain.llm_provider} base_url={cfg.brain.effective_base_url}")
    print(f"[vision] enabled={cfg.capabilities.vision.enabled} provider={cfg.capabilities.vision.provider} model={cfg.capabilities.vision.model}")

    brain = Brain(cfg.brain, vision_model=cfg.capabilities.vision.model)

    ok, msg = await brain.healthcheck()
    print(f"[healthcheck] ok={ok} {msg}")
    if not ok:
        print("ОШИБКА: в LM Studio нет загруженной модели. Загрузите модель и включите Local Server.")
        return 2

    try:
        names = (await brain._resolve_loaded_model())[1]
    except Exception as exc:  # noqa
        print(f"ОШИБКА резолва моделей: {exc}")
        return 2
    print(f"[models] загружено: {names}")

    chosen = brain._pick_vision_model(names)
    print(f"[vision] выбранная VLM: {chosen}")

    png = _test_png()
    try:
        text = await brain.vision(png, "Кратко опиши цвет этого квадрата по-русски.")
        print(f"[vision] ОТВЕТ: {text!r}")
    except Exception as exc:  # noqa
        print(f"[vision] ОШИБКА: {exc}")
        print("Возможно модель не multimodal. Загрузите VLM в LM Studio.")
        return 3

    print("OK: зрение работает против LM Studio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
