from __future__ import annotations

import asyncio
from types import SimpleNamespace

from uni.brain import Brain
from uni.config import BrainConfig


class ModelsEndpoint:
    def __init__(self, *model_ids: str):
        self._model_ids = model_ids

    async def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._model_ids])


def make_brain(configured: str, *loaded: str) -> Brain:
    brain = Brain(BrainConfig(model=configured))
    brain.client = SimpleNamespace(models=ModelsEndpoint(*loaded))
    return brain


def test_auto_selects_loaded_lm_studio_model() -> None:
    brain = make_brain("auto", "qwen3.5-9b")

    ok, detail = asyncio.run(brain.healthcheck())

    assert ok is True
    assert brain.model == "qwen3.5-9b"
    assert "qwen3.5-9b" in detail


def test_stale_config_falls_back_to_loaded_model() -> None:
    brain = make_brain("old-model", "current-model")

    ok, detail = asyncio.run(brain.healthcheck())

    assert ok is True
    assert brain.model == "current-model"
    assert "автоматически" in detail


def test_explicit_loaded_model_remains_selected() -> None:
    brain = make_brain("preferred", "other", "preferred")

    ok, _ = asyncio.run(brain.healthcheck())

    assert ok is True
    assert brain.model == "preferred"


def test_no_loaded_models_has_actionable_error() -> None:
    brain = make_brain("auto")

    ok, detail = asyncio.run(brain.healthcheck())

    assert ok is False
    assert "нет загруженной модели" in detail


def test_explicit_vision_model_is_not_replaced() -> None:
    brain = Brain(BrainConfig(model="auto", vision_model="vision-model"))
    brain.client = SimpleNamespace(models=ModelsEndpoint("text-model"))

    asyncio.run(brain.healthcheck())

    assert brain.model == "text-model"
    assert brain.vision_model == "vision-model"
