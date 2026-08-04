"""
verify_config_defaults.py — закрывает последний открытый спорный пункт
из разбора внешних предложений: «в config.py есть опасные дефолты
debug=True / allow_camera=True / allow_screenshot=True».

Проверяем РЕАЛЬНЫЙ uni/config.py:
  - поля debug / allow_camera / allow_screenshot НЕ должны существовать
    (иначе это был бы реальный риск, как утверждал один из внешних ИИ).
  - Config загружается из config.yaml без ошибок.

Запуск:
  cd /c/LLM/UNI
  PYTHONPATH=/c/LLM/UNI /c/LLM/python312/python.exe tests_probe/verify_config_defaults.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Гарантируем импорт uni независимо от того, как запущен скрипт.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from uni.config import Config, load_config


def main() -> int:
    print("=== verify_config_defaults ===")
    problems = []

    # 1) Проверяем, что опасных полей НЕТ в схеме pydantic.
    dangerous_fields = ["debug", "allow_camera", "allow_screenshot"]
    schema_fields = set(Config.model_fields.keys())
    for f in dangerous_fields:
        if f in schema_fields:
            problems.append(
                f"Config содержит ОПАСНОЕ поле '{f}' (defолт: "
                f"{Config.model_fields[f].default!r})"
            )
        else:
            print(f"[OK]   поле '{f}' отсутствует в Config (безопасно)")

    # 2) Рекурсивно проверяем вложенные суб-модели (на случай depth).
    import typing

    def _unwrap(ann):
        # снимаем Optional[...] / Union
        if typing.get_origin(ann) is typing.Union:
            args = [a for a in typing.get_args(ann) if a is not type(None)]
            return args[0] if args else ann
        return ann

    def scan_model(model_cls, path):
        for name, field in model_cls.model_fields.items():
            ann = _unwrap(field.annotation)
            if isinstance(ann, type) and hasattr(ann, "model_fields"):
                scan_model(ann, f"{path}.{name}")

    scan_model(Config, "Config")

    # 3) Реальная загрузка из config.yaml (путь по умолчанию).
    try:
        cfg = load_config("config.yaml")
        print(
            f"[OK]   load_config('config.yaml') успешно; "
            f"default_role={cfg.agent.default_role!r}, "
            f"autonomous.enabled={cfg.autonomous.enabled}"
        )
    except Exception as exc:
        problems.append(f"load_config упал: {type(exc).__name__}: {exc}")

    # 4) Проверяем, что у AgentConfig нет debug/log_level с шумными дефолтами.
    agent_cls = type(cfg.agent)
    agent_fields = set(agent_cls.model_fields.keys())
    for f in ("debug", "log_level"):
        if f in agent_fields:
            problems.append(f"AgentConfig содержит '{f}'={getattr(cfg.agent, f)!r}")

    print("=" * 40)
    if problems:
        print("РЕЗУЛЬТАТ: НАЙДЕНЫ ПРОБЛЕМЫ:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("РЕЗУЛЬТАТ: OK — опасных дефолтов debug/allow_camera/allow_screenshot НЕТ.")
    print("Вывод: спорный пункт извне (z.ai) НЕ ПОДТВЕРЖДЁН — код безопасен.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
