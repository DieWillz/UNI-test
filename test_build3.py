"""Тест-скрипт Build 3 — Working Memory."""

import asyncio
from pathlib import Path

from uni.working_memory import WorkingMemory
from uni.capabilities.memory import MemoryCapability
from uni.config import MemoryConfig
from uni.contracts import ToolResult


def test_working_memory_sync():
    test_path = Path("memory/test_working.json")
    if test_path.exists():
        test_path.unlink()

    wm = WorkingMemory(test_path)

    # set/get
    wm.set("last_command", "открой Chrome")
    assert wm.get("last_command") == "открой Chrome"
    assert wm.get("missing_key", "default") == "default"

    # list_keys
    wm.set("step", 1)
    assert set(wm.list_keys()) == {"last_command", "step"}

    # delete
    wm.delete("step")
    assert "step" not in wm.list_keys()

    # persistence — новый инстанс должен подхватить сохранённое
    wm2 = WorkingMemory(test_path)
    assert wm2.get("last_command") == "открой Chrome"

    # get_context — базовый формат
    ctx = wm2.get_context(max_tokens=4000)
    assert "last_command: открой Chrome" in ctx

    # get_context — обрезка при маленьком лимите не должна падать
    wm2.set("a", "x" * 500)
    wm2.set("b", "y" * 500)
    small_ctx = wm2.get_context(max_tokens=10)  # ~40 символов бюджет
    assert len(small_ctx) <= 10 * 4 + 50  # с запасом на границы строк

    # clear
    wm2.clear()
    assert wm2.list_keys() == []

    # повреждённый файл памяти не должен ронять агент при старте
    test_path.write_text("{not valid json", encoding="utf-8")
    wm3 = WorkingMemory(test_path)
    assert wm3.list_keys() == []

    test_path.unlink()
    print("✅ Build 3: WorkingMemory — все проверки пройдены")


async def test_memory_capability():
    test_path = Path("memory/test_capability.json")
    if test_path.exists():
        test_path.unlink()

    cap = MemoryCapability(MemoryConfig(path=str(test_path)))
    assert cap.name == "memory"
    assert cap.tools == ["remember", "recall", "forget"]

    await cap.setup()

    r1 = await cap.remember("last_command", "открой Chrome")
    assert isinstance(r1, ToolResult)
    assert r1.success is True

    r2 = await cap.recall("last_command")
    assert r2.success is True
    assert r2.data == {"key": "last_command", "value": "открой Chrome"}

    r3 = await cap.recall("no_such_key")
    assert r3.success is False
    assert r3.error is not None

    r4 = await cap.forget("last_command")
    assert r4.success is True

    r5 = await cap.recall("last_command")
    assert r5.success is False

    await cap.shutdown()
    test_path.unlink()
    print("✅ Build 3: MemoryCapability — все проверки пройдены")


if __name__ == "__main__":
    test_working_memory_sync()
    asyncio.run(test_memory_capability())
