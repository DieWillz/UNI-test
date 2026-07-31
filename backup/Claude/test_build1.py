"""Тест-скрипт Build 1 — Skeleton & Config."""

from uni.config import (
    load_config,
    BrainConfig,
    BrowserConfig,
    ComputerConfig,
    SpeechConfig,
    VisionConfig,
    AgentConfig,
    MemoryConfig,
    Config,
)


def test():
    cfg = load_config("config.yaml")

    # --- root types ---
    assert isinstance(cfg, Config)
    assert isinstance(cfg.brain, BrainConfig)
    assert isinstance(cfg.agent, AgentConfig)
    assert isinstance(cfg.memory, MemoryConfig)

    # --- brain defaults ---
    assert cfg.brain.base_url == "http://localhost:1234/v1"
    assert cfg.brain.model == "qwen2.5-7b-instruct"
    assert cfg.brain.temperature == 0.3
    assert cfg.brain.max_tokens == 2000

    # --- capabilities are typed sub-models, not raw dicts ---
    assert set(cfg.capabilities.keys()) == {"browser", "computer", "speech", "vision"}
    assert isinstance(cfg.capabilities["browser"], BrowserConfig)
    assert isinstance(cfg.capabilities["computer"], ComputerConfig)
    assert isinstance(cfg.capabilities["speech"], SpeechConfig)
    assert isinstance(cfg.capabilities["vision"], VisionConfig)

    assert cfg.capabilities["browser"].headless is False
    assert cfg.capabilities["browser"].viewport == {"width": 1280, "height": 720}
    assert cfg.capabilities["computer"].use_uia is True
    assert cfg.capabilities["computer"].failsafe is True
    assert cfg.capabilities["speech"].tts_voice == "ru_RU-irina-medium"
    assert cfg.capabilities["speech"].sample_rate == 16000
    assert cfg.capabilities["vision"].enabled is True
    assert cfg.capabilities["vision"].model == "llava"

    # --- agent / memory ---
    assert cfg.agent.default_role == "assistant"
    assert cfg.agent.cycle_interval == 3.0
    assert cfg.agent.max_retries == 3
    assert cfg.agent.verification_enabled is True
    assert cfg.memory.path == "memory/working.json"
    assert cfg.memory.max_context_tokens == 4000

    # --- missing file raises FileNotFoundError, not a silent default ---
    try:
        load_config("does_not_exist.yaml")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass

    # --- empty capabilities section still fills in typed defaults ---
    import yaml
    from pathlib import Path

    tmp = Path("test_empty_capabilities.yaml")
    tmp.write_text(
        yaml.dump({"brain": {}, "capabilities": {}, "agent": {}, "memory": {}}),
        encoding="utf-8",
    )
    cfg2 = load_config(str(tmp))
    assert isinstance(cfg2.capabilities["speech"], SpeechConfig)
    assert cfg2.capabilities["speech"].stt_model == "base"
    tmp.unlink()

    print("✅ Build 1: все проверки пройдены")


if __name__ == "__main__":
    test()
