"""Проверка: Vision описывает кадры/экран по-русски (Фикс А).

Мокает Gradio-Vision, чтобы не требовать живой модели. Проверяет, что:
1. Кириллический промпт НЕ подменяется на английский шаблон.
2. К промпту всегда добавляется «Отвечай только по-русски.».
3. Дефолтные промпты (analyze_desktop / analyze_file) — русские.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.config import load_config
from uni.capabilities.vision import VisionCapability


def _real_image() -> Image.Image:
    return Image.new("RGB", (32, 32), (10, 20, 30))


def _build_vision(monkeypatch):
    cfg = load_config()
    cfg.capabilities.vision.provider = "gradio"
    cfg.capabilities.vision.enabled = True
    captured = {}

    def fake_gradio_predict(image, prompt):
        captured["prompt"] = prompt
        return "ответ на русском"

    cap = VisionCapability.__new__(VisionCapability)
    cap.config = cfg
    cap.brain = None
    cap.session = None
    cap.save_dir = Path(".uni-logs")
    cap._gradio_client = None
    cap._gradio_lock = None
    monkeypatch.setattr(cap, "_gradio_predict", fake_gradio_predict)
    return cap, captured


async def _ready(cap):
    await asyncio.sleep(0)
    cap._gradio_lock = asyncio.Lock()
    return cap


@pytest.mark.asyncio
async def test_cyrillic_prompt_not_replaced(monkeypatch):
    cap, captured = _build_vision(monkeypatch)
    await _ready(cap)
    await cap._ask(_real_image(), "Что на экране XToys?", preserve_prompt=False)
    p = captured["prompt"]
    # Ветка preserve_prompt=False: используется русский шаблон (английский не должен появиться)
    assert "Describe this browser screenshot" not in p
    assert ("опиши" in p.lower()) or ("опис" in p.lower())


@pytest.mark.asyncio
async def test_preserve_prompt_gets_russian_suffix(monkeypatch):
    cap, captured = _build_vision(monkeypatch)
    await _ready(cap)
    await cap._ask(_real_image(), "Return only JSON {\"x\":1}", preserve_prompt=True)
    p = captured["prompt"]
    assert "Return only JSON" in p
    assert p.endswith("Отвечай только по-русски.")


@pytest.mark.asyncio
async def test_default_desktop_prompt_is_russian(monkeypatch):
    cap, captured = _build_vision(monkeypatch)
    await _ready(cap)
    await cap.analyze_desktop()
    p = captured["prompt"]
    assert ("рабочий стол" in p.lower()) or ("опиши" in p.lower())
    assert "Describe the visible Windows desktop" not in p


@pytest.mark.asyncio
async def test_default_camera_file_prompt_is_russian(monkeypatch, tmp_path):
    cap, captured = _build_vision(monkeypatch)
    await _ready(cap)
    img = tmp_path / "cam.png"
    _real_image().save(img, "PNG")
    await cap.analyze_file(str(img), "опиши кадр")
    p = captured["prompt"]
    assert ("камер" in p.lower()) or ("опиши" in p.lower())
    assert "Describe this camera frame" not in p
