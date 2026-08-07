from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
import yaml

class BrainConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "auto"
    vision_model: Optional[str] = None
    vision_base_url: Optional[str] = None
    vision_api_key: Optional[str] = None
    temperature: float = 0.8
    max_tokens: int = 2000
    timeout_seconds: float = 20.0

class AgentCursorConfig(BaseModel):
    """Page overlay cursor labeled UNI — does not move the OS mouse."""
    enabled: bool = True
    label: str = "UNI"
    move_ms: int = Field(default=220, ge=0, le=2000)
    hide_after_ms: int = Field(default=1200, ge=0, le=10_000)


class BrowserConfig(BaseModel):
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    channel: Optional[str] = "chrome"
    user_data_dir: str = ".uni-browser-profile"
    search_engine: str = "https://www.bing.com/search?q={query}"
    image_search_engine: str = "https://yandex.ru/images/search?text={query}"
    cdp_url: Optional[str] = None  # e.g. "http://127.0.0.1:9222" to attach to your running Chrome
    agent_cursor: AgentCursorConfig = Field(default_factory=AgentCursorConfig)

class ComputerConfig(BaseModel):
    use_uia: bool = True
    failsafe: bool = True
    mouse_move_duration: float = Field(default=0.35, ge=0.0, le=2.0)
    action_badge: bool = True  # desktop «UNI» badge near pyautogui clicks
    action_badge_label: str = "UNI"

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
    autonomous_physical: bool = Field(default=False)  # explicit opt-in to move the device unsupervised


class DemoXToysSettings(BaseModel):
    """Часть демо-сценария «Игрушки Uni» (python -m uni --demo xtoys)."""
    url: str = ""  # пусто -> берётся из XToysConfig.url
    wander_seconds: float = Field(default=12.0, ge=1.0, le=300.0)
    pet_points: int = Field(default=6, ge=1, le=32)


class DemoMouseSettings(BaseModel):
    label_text: str = "Uni"
    speed: float = Field(default=1.0, ge=0.1, le=5.0)
    fps: int = Field(default=90, ge=30, le=240)
    failsafe: bool = True


class DemoSettings(BaseModel):
    xtoys: DemoXToysSettings = Field(default_factory=DemoXToysSettings)
    mouse: DemoMouseSettings = Field(default_factory=DemoMouseSettings)


class ContextFeedConfig(BaseModel):
    """Внешние источники контекста/стиля для чат-хаба (опц., безопасно выключено).

    Внешний текст всегда считается недоверенными данными (как в council).
    """
    enabled: bool = False
    allow_external_scrape: bool = Field(
        default=False,  # безопасность: NSFW/внешний скрейп по умолчанию ВЫКЛ
    )
    injection_rate: float = Field(default=0.6, ge=0.0, le=1.0)
    feeds: list[str] = Field(default_factory=list)
    tonal_mode: str = "playful"  # playful | spicy | custom


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
    autonomous: "AutonomousConfig" = Field(default_factory=lambda: AutonomousConfig())

class LoggingConfig(BaseModel):
    enabled: bool = True
    directory: str = ".uni-logs"

class AutonomousConfig(BaseModel):
    """Hands-free mode: UNI acts without user commands (watches, talks, drives XToys)."""
    enabled: bool = False
    auto_start_session: bool = Field(default=True)  # start the hands-free session right after `python -m uni`
    vision_interval_seconds: float = Field(default=15.0, ge=3.0, le=120.0)
    speech_interval_seconds: float = Field(default=7.0, ge=2.0, le=60.0)
    device_interval_seconds: float = Field(default=2.0, ge=1.0, le=60.0)
    conductor_interval_seconds: float = Field(default=25.0, ge=5.0, le=300.0)
    # The device never moves unless the user explicitly acknowledges it in two places:
    # config.capabilities.xtoys.autonomous_physical AND config.autonomous.enabled.
    enable_device_motion: bool = Field(default=False)  # convenience mirror of xtoys.autonomous_physical
    require_connect: bool = Field(default=False)  # if True, do not move the device until XToys is connected

class MemoryConfig(BaseModel):
    path: str = "memory/working.json"
    max_context_tokens: int = 4000
    max_dialogue_turns: int = Field(default=50, ge=5, le=500)

class CouncilConfig(BaseModel):
    """Development council automation (MANIFESTO v2.6 §7, COUNCIL-002).

    Replaces the manual copy-paste loop between AI participants. Participants are
    queried through the cheapest available transport: API when the model is free/
    local, browser automation when it is a paid closed web chat. Advisor output is
    always treated as untrusted data and never invokes a UNI tool.

    Per MANIFESTO v2.6 §7, the browser adapter is ENABLED by default for FREE web
    tiers (so users without money can reach strong models without paying for API),
    but it must respect fair-use conditions: informed consent about possible ToS
    violation, rate limiting via reasonable pauses, and it must NEVER automate
    consumer paid subscriptions (ChatGPT Plus, Gemini Advanced, ...) as a stand-in
    for the official API.
    """
    enabled: bool = True
    artifacts_dir: str = ".uni-council"
    concurrency: int = Field(default=3, ge=1, le=8)
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=600.0)
    collect_signatures: bool = True
    # Browser transport (MANIFESTO v2.6 §7).
    browser_enabled: bool = True  # on by default for free web tiers
    inform_tos: bool = True  # tell the user automation may breach a service ToS
    free_tier_only: bool = True  # never automate paid consumer subscriptions
    min_interval_seconds: float = Field(default=8.0, gt=0.0, le=120.0)  # rate limit / pauses
    # Separate browser profile so web-AI sessions never mix with user bank/mail/intimate.
    browser_profile: str = ".uni-council-browser-profile"
    # API endpoints for council participants (OpenRouter / Groq / ...). Keys come from the
    # local config only — never from code. WebUI settings panel edits this block.
    api_endpoints: dict[str, Any] = Field(
        default_factory=lambda: {
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "",  # set in local config.yaml (secret)
            },
            "groq": {
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": "",  # set in local config.yaml (secret)
            },
        }
    )

class Config(BaseModel):
    brain: BrainConfig = Field(default_factory=BrainConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    demo: DemoSettings = Field(default_factory=DemoSettings)
    context: ContextFeedConfig = Field(default_factory=ContextFeedConfig)

def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return Config(**data)
    return Config()
