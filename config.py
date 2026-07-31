from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

class BrainConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen2.5-7b-instruct-1m"
    vision_model: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 2000

class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720

class ComputerConfig(BaseModel):
    use_uia: bool = True
    failsafe: bool = True

class SpeechConfig(BaseModel):
    stt_model: str = "base"
    tts_voice: str = "ru_RU-irina-medium"
    sample_rate: int = 16000

class VisionConfig(BaseModel):
    enabled: bool = False
    model: str = "qwen3.5-9b"
    resize_width: int = 320
    resize_height: int = 240
    save_screenshots: bool = False

class CapabilitiesConfig(BaseModel):
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    computer: ComputerConfig = Field(default_factory=ComputerConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)

class AgentConfig(BaseModel):
    default_role: str = "assistant"
    cycle_interval: float = 2.0
    max_retries: int = 3
    verification_enabled: bool = False

class MemoryConfig(BaseModel):
    path: str = "memory/working.json"
    max_context_tokens: int = 4000

class Config(BaseModel):
    brain: BrainConfig = Field(default_factory=BrainConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return Config(**data)
    return Config()
