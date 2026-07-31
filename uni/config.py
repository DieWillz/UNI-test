"""
uni.config — конфигурация проекта UNI.

Назначение:
    Единая точка загрузки и валидации конфигурации агента из config.yaml.
    Все остальные модули (Brain, Capabilities, Memory, EventLoop) читают
    настройки ТОЛЬКО через объект Config, возвращаемый load_config().

Зависимости:
    pydantic>=2, pyyaml

Пример использования:
    >>> from uni.config import load_config
    >>> cfg = load_config("config.yaml")
    >>> cfg.brain.model
    'qwen2.5-7b-instruct'
    >>> cfg.capabilities["speech"].tts_voice
    'ru_RU-irina-medium'

Известные ограничения:
    - load_config() не делает hot-reload: конфиг читается один раз при старте.
    - Поле Config.capabilities типизировано как dict (по контракту координатора),
      но load_config() кладёт туда НЕ сырые dict, а уже провалидированные
      pydantic-объекты (BrowserConfig, ComputerConfig, SpeechConfig, VisionConfig)
      под ключами "browser" / "computer" / "speech" / "vision".
      Это важно: тест-скрипт Nemotron делает
          SpeechCapability(cfg.capabilities["speech"])
      и ожидает на входе готовый SpeechConfig, а не dict. Если кто-то из
      команды меняет эту логику — см. секцию "ВАЖНОЕ ЗАМЕЧАНИЕ ПО КОНТРАКТУ"
      в статус-отчёте Build 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Capability-level configs
# ---------------------------------------------------------------------------

class BrainConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen2.5-7b-instruct"
    temperature: float = 0.3
    max_tokens: int = 2000


class BrowserConfig(BaseModel):
    headless: bool = False
    viewport: dict = Field(default_factory=lambda: {"width": 1280, "height": 720})


class ComputerConfig(BaseModel):
    use_uia: bool = True
    failsafe: bool = True


class SpeechConfig(BaseModel):
    stt_model: str = "base"
    tts_voice: str = "ru_RU-irina-medium"
    sample_rate: int = 16000


class VisionConfig(BaseModel):
    enabled: bool = True
    model: str = "llava"


class AgentConfig(BaseModel):
    default_role: str = "assistant"
    cycle_interval: float = 3.0
    max_retries: int = 3
    verification_enabled: bool = True


class MemoryConfig(BaseModel):
    path: str = "memory/working.json"
    max_context_tokens: int = 4000


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

# Registry of capability name -> its Pydantic model.
# Build 4 (Capability Registry) and Build 5-8 (Nemotron) rely on these keys
# existing exactly as "browser" / "computer" / "speech" / "vision".
CAPABILITY_MODELS: dict[str, type[BaseModel]] = {
    "browser": BrowserConfig,
    "computer": ComputerConfig,
    "speech": SpeechConfig,
    "vision": VisionConfig,
}


class Config(BaseModel):
    brain: BrainConfig
    capabilities: dict[str, Any]
    agent: AgentConfig
    memory: MemoryConfig


def load_config(path: str = "config.yaml") -> Config:
    """
    Загружает и валидирует config.yaml.

    Raises:
        FileNotFoundError: если файл не существует.
        pydantic.ValidationError: если значения в YAML не проходят валидацию.
    """
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {cfg_path.resolve()}. "
            f"Скопируйте config.yaml из корня проекта или укажите верный путь."
        )

    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    raw_capabilities = raw.get("capabilities", {}) or {}
    capabilities: dict[str, BaseModel] = {}
    for name, model_cls in CAPABILITY_MODELS.items():
        capabilities[name] = model_cls(**raw_capabilities.get(name, {}))

    return Config(
        brain=BrainConfig(**raw.get("brain", {})),
        capabilities=capabilities,
        agent=AgentConfig(**raw.get("agent", {})),
        memory=MemoryConfig(**raw.get("memory", {})),
    )
