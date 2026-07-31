from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

class BrainConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "qwen2.5-7b-instruct-1m"
    vision_model: Optional[str] = None
    vision_base_url: Optional[str] = None
    vision_api_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 2000
    timeout_seconds: float = 20.0

class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    channel: Optional[str] = "chrome"
    user_data_dir: str = ".uni-browser-profile"
    search_engine: str = "https://www.bing.com/search?q={query}"
    image_search_engine: str = "https://yandex.ru/images/search?text={query}"

class ComputerConfig(BaseModel):
    use_uia: bool = True
    failsafe: bool = True
    mouse_move_duration: float = Field(default=0.35, ge=0.0, le=2.0)

class CameraConfig(BaseModel):
    enabled: bool = True
    device_index: int = Field(default=0, ge=0, le=16)
    backend: str = "dshow"
    width: int = Field(default=1280, ge=160, le=3840)
    height: int = Field(default=720, ge=120, le=2160)
    min_brightness: float = Field(default=15.0, ge=0.0, le=255.0)
    sample_interval_seconds: float = Field(default=60.0, ge=5.0, le=3600.0)
    reminder_interval_seconds: float = Field(default=1800.0, ge=60.0, le=7200.0)
    default_watch_seconds: float = Field(default=600.0, ge=10.0, le=28800.0)
    max_watch_seconds: float = Field(default=28800.0, ge=60.0, le=86400.0)

class SpeechConfig(BaseModel):
    stt_model: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_beam_size: int = Field(default=1, ge=1, le=5)
    microphone_gain: float = Field(default=1.0, ge=0.1, le=20.0)
    voice_activation_threshold: float = Field(default=0.004, ge=0.0005, le=0.2)
    voice_silence_seconds: float = Field(default=0.8, ge=0.2, le=3.0)
    max_utterance_seconds: float = Field(default=8.0, ge=2.0, le=30.0)
    tts_provider: str = "silero"
    tts_voice: str = "ru_RU-irina-medium.onnx"
    silero_model: str = "v5_5_ru"
    silero_speaker: str = "xenia"
    silero_sample_rate: int = Field(default=48000, ge=8000, le=48000)
    sample_rate: int = 16000
    listen_duration: float = Field(default=2.5, ge=0.5, le=30.0)
    input_device: Optional[int | str] = None
    output_device: Optional[int | str] = None

class VisionConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "qwen3.5-9b"
    gradio_url: str = "http://127.0.0.1:7860/"
    gradio_api_name: str = "/answer_question"
    gradio_fallback_api_name: Optional[str] = "/answer_question_1"
    resize_width: int = 320
    resize_height: int = 240
    save_screenshots: bool = False

class XToysConfig(BaseModel):
    url: str = "https://xtoys.app"
    max_intensity: int = Field(default=50, ge=0, le=100)

class CapabilitiesConfig(BaseModel):
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    computer: ComputerConfig = Field(default_factory=ComputerConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    xtoys: XToysConfig = Field(default_factory=XToysConfig)

class AgentConfig(BaseModel):
    default_role: str = "xtoys_mistress"
    cycle_interval: float = 2.0
    max_retries: int = 3
    verification_enabled: bool = False
    input_mode: str = "mixed"
    speak_responses: bool = True
    max_parallel_tasks: int = Field(default=3, ge=1, le=8)
    max_pending_tasks: int = Field(default=6, ge=1, le=32)
    task_timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    exploration_steps: int = Field(default=3, ge=1, le=5)
    visual_ui_max_steps: int = Field(default=20, ge=4, le=40)
    response_max_chars: int = Field(default=700, ge=120, le=4000)
    spoken_response_max_chars: int = Field(default=320, ge=80, le=1200)

class LoggingConfig(BaseModel):
    enabled: bool = True
    directory: str = ".uni-logs"

class MemoryConfig(BaseModel):
    path: str = "memory/working.json"
    max_context_tokens: int = 4000
    max_dialogue_turns: int = Field(default=50, ge=5, le=500)

class Config(BaseModel):
    brain: BrainConfig = Field(default_factory=BrainConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return Config(**data)
    return Config()
