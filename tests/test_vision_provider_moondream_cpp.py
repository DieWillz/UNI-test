"""Тесты CPU-first VLM (P-02, 2026-08-17)."""
from __future__ import annotations

import pytest

from uni.capabilities.vision_providers.moondream_cpp import MoondreamCppProvider


def test_provider_init_defaults():
    p = MoondreamCppProvider()
    assert p.base_url == "http://127.0.0.1:1236/v1"
    assert p.api_key == "uni-local"
    assert p.model == "moondream2"


def test_provider_health_check_offline():
    """VLM не поднят — health_check вернёт ok=False (без падения)."""
    p = MoondreamCppProvider(base_url="http://127.0.0.1:1/v1")
    result = p.health_check()
    assert result["ok"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_provider_describe_offline():
    """VLM не поднят — describe вернёт ok=False (без падения)."""
    p = MoondreamCppProvider(base_url="http://127.0.0.1:1/v1", timeout_seconds=1.0)
    result = await p.describe("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=", "test")
    assert result["ok"] is False
    assert result["provider"] == "moondream-cpp"


@pytest.mark.asyncio
async def test_provider_accepts_data_url():
    """describe() должна принимать как raw base64, так и data URL."""
    p = MoondreamCppProvider(base_url="http://127.0.0.1:1/v1", timeout_seconds=0.5)
    data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
    result = await p.describe(data_url, "test")
    assert result["ok"] is False  # offline, но не упал
