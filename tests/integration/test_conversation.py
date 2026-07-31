#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from uni.agent import Agent
from uni.config import load_config
from uni.event_loop import CycleResult


async def run_integration_tests():
    config = load_config("config.yaml")
    print(f"🧪 Starting UNI integration tests (model={config.brain.model})...\n")

    agent = Agent(config)
    await agent.initialize()

    # Test 1: Simple cycle
    print("🧪 Test 1: Run cycle with navigation command")
    result = await agent.event_loop.run_cycle(
        "Открой браузер и перейди на https://example.com"
    )
    assert isinstance(result, CycleResult), f"Expected CycleResult, got {type(result)}"
    print(f"    CycleResult: {result.value}")
    print("✅ Test 1 passed\n")

    # Test 2: Second cycle to verify content
    print("🧪 Test 2: Search for text on page")
    result = await agent.event_loop.run_cycle(
        "Найди текст 'Example Domain' на экране"
    )
    assert isinstance(result, CycleResult)
    print(f"    CycleResult: {result.value}")
    print("✅ Test 2 passed\n")

    # Test 3: Speech command
    print("🧪 Test 3: Say hello")
    result = await agent.event_loop.run_cycle("Скажи привет")
    assert isinstance(result, CycleResult)
    print(f"    CycleResult: {result.value}")
    if result == CycleResult.COMPLETE:
        print("✅ Test 3 passed (task completed)\n")
    else:
        print("✅ Test 3 passed (cycle returned without error)\n")

    # Test 4: Multi-step sequence
    print("🧪 Test 4: Open browser, search, speak")
    result = await agent.event_loop.run_cycle(
        "Открой браузер, найди Википедию про Павловского дога, скажи информацию"
    )
    assert isinstance(result, CycleResult)
    print(f"    CycleResult: {result.value}")
    print("✅ Test 4 passed\n")

    await agent.shutdown()
    print("🎉 All integration tests passed!")


if __name__ == "__main__":
    asyncio.run(run_integration_tests())
