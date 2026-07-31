#!/usr/bin/env python3
"""
Тест планировщика UNI для Build 12.
Запускать из корня проекта: python test_planner_basic.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from uni.config import load_config
from uni.brain import Brain
from uni.capabilities.registry import CapabilityRegistry
from uni.capabilities.computer import ComputerCapability
from uni.capabilities.browser import BrowserCapability
from uni.capabilities.speech import SpeechCapability
from uni.capabilities.vision import VisionCapability
from uni.capabilities.memory import MemoryCapability
from uni.tools.executors import ToolExecutor
from uni.planner import PlannerImpl
from uni.planner_interface import TaskQueueImpl
from uni.working_memory import WorkingMemory

async def test_basic_planner():
    print("=" * 60)
    print("Запуск теста планировщика UNI")
    print("=" * 60)

    # 1. Загружаем конфиг
    cfg = load_config("config.yaml")
    print(f"✓ Конфиг загружен. Модель: {cfg.brain.model}")

    # 2. Создаём Brain
    brain = Brain(cfg)
    print("✓ Brain инициализирован")

    # 3. Создаём и регистрируем моки (заглушки) для способностей
    # Мы не будем реально запускать браузер или двигать мышь, чтобы тест был быстрым
    registry = CapabilityRegistry()

    class MockComputer(ComputerCapability):
        async def execute(self, tool_name: str, args: dict):
            print(f"  [COMPUTER] Выполняется: {tool_name}({args})")
            return {"success": True}

    class MockBrowser(BrowserCapability):
        async def execute(self, tool_name: str, args: dict):
            print(f"  [BROWSER] Выполняется: {tool_name}({args})")
            return {"success": True, "url": args.get("url")}

    class MockSpeech(SpeechCapability):
        async def execute(self, tool_name: str, args: dict):
            print(f"  [SPEECH] Выполняется: {tool_name}({args})")
            return {"success": True}

    class MockVision(VisionCapability):
        async def execute(self, tool_name: str, args: dict):
            print(f"  [VISION] Выполняется: {tool_name}({args})")
            return {"success": True}

    class MockMemory(MemoryCapability):
        async def execute(self, tool_name: str, args: dict):
            print(f"  [MEMORY] Выполняется: {tool_name}({args})")
            return {"success": True}

    registry.register(MockComputer(use_uia=False))
    registry.register(MockBrowser(headless=True))
    registry.register(MockSpeech(stt_model="tiny", tts_voice="test"))
    registry.register(MockVision(brain, cfg))
    registry.register(MockMemory(cfg.memory))

    print("✓ Моки способностей зарегистрированы")

    # 4. Инициализируем ToolExecutor и Planner
    tool_executor = ToolExecutor(registry)
    planner = PlannerImpl(brain, registry, cfg)
    task_queue = TaskQueueImpl()
    memory = WorkingMemory(Path(cfg.memory.path))

    print("✓ ToolExecutor и Planner инициализированы")

    # 5. Тестовые сценарии
    test_scenarios = [
        "открой браузер и зайди на youtube.com",
        "напиши в блокноте 'привет мир'",
        "сделай скриншот экрана",
    ]

    for i, goal in enumerate(test_scenarios, 1):
        print(f"\n--- Сценарий {i}: '{goal}' ---")

        # Планируем
        tasks = await planner.plan(goal, [])

        if not tasks:
            print(f"✗ Не удалось сгенерировать план для '{goal}'")
            continue

        print(f"✓ План сгенерирован. Шагов: {len(tasks)}")
        for idx, task in enumerate(tasks, 1):
            print(f"  {idx}. {task.action.name}({task.action.params}) [prio={task.priority}, deps={task.depends_on}]")

            # Эмулируем выполнение
            result = await tool_executor.execute(task.action.name, task.action.params)
            await task_queue.mark_completed(task.id)

            if result.get("success"):
                print(f"    ✓ Выполнено успешно")
            else:
                print(f"    ✗ Ошибка: {result.get('error')}")

        print("✓ Сценарий выполнен")

    print("\n" + "=" * 60)
    print("Все тесты завершены.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_basic_planner())
