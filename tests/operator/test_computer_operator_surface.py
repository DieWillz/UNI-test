from __future__ import annotations

import pytest

from uni.capabilities.computer import ComputerCapability
from uni.contracts import ToolResult


@pytest.mark.asyncio
async def test_computer_execute_exposes_bounded_uia_snapshot(monkeypatch) -> None:
    computer = ComputerCapability(action_badge_enabled=False, use_human_motion=False)

    async def fake(max_elements=120):
        return ToolResult(success=True, data={"active_window":{}, "elements":[{"name":"X"}]})

    monkeypatch.setattr(computer, "inspect_accessible_elements", fake, raising=False)
    result = await computer.execute("inspect_accessible_elements", max_elements=40)
    assert result.success is True
    assert result.data["elements"][0]["name"] == "X"
