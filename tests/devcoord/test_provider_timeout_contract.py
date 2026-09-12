from __future__ import annotations

import time

import pytest

from uni.devcoord.models import HandoffPackage, ProviderConfig, ProviderResult
from uni.devcoord.providers import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_api_provider_timeout_returns_error_result_instead_of_raising():
    config = ProviderConfig(
        id="api-test",
        display_name="API Test",
        transport="api",
        enabled=True,
        api_cost="free",
        base_url="http://127.0.0.1:1/v1",
        model="test-model",
        timeout_seconds=5.0,
    )
    config.timeout_seconds = 0.01
    provider = OpenAICompatibleProvider(config)

    def slow_request(_prompt: str) -> ProviderResult:
        time.sleep(0.05)
        return ProviderResult(provider_id=config.id, transport="api", content="late")

    provider._request_sync = slow_request
    handoff = HandoffPackage(
        task_id="task-1",
        goal="test timeout",
        instructions="return a proposal",
        to_agent=config.id,
    )

    result = await provider.request(handoff)

    assert result.provider_id == config.id
    assert result.content == ""
    assert result.error and "timeout" in result.error.lower()
