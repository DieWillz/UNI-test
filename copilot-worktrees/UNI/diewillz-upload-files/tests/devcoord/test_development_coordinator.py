from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from uni.devcoord.artifacts import ArtifactCollector
from uni.devcoord.coordinator import DevelopmentCoordinator
from uni.devcoord.models import DevelopmentTask, ProviderConfig, ProviderResult, TaskStatus
from uni.devcoord.providers import DevelopmentProvider, ProviderRegistry
from uni.devcoord.store import CoordinationStore


class FakeProvider(DevelopmentProvider):
    async def request(self, handoff):
        return ProviderResult(
            provider_id=self.config.id,
            transport=self.config.transport,
            content=f"reviewed {handoff.task_id}; previous={len(handoff.previous_results)}",
        )


class FakeRegistry(ProviderRegistry):
    def build(self, provider_id):
        return FakeProvider(self.configs[provider_id])


def api_config(provider_id: str) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        display_name=provider_id,
        transport="api",
        enabled=True,
        api_cost="free",
        base_url="http://127.0.0.1:1234/v1",
        model="test",
    )


class DevelopmentCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def test_artifact_is_bounded_to_workspace_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "design.md"
            target.write_text("hello UNI", encoding="utf-8")
            artifact = ArtifactCollector(root).collect(["design.md"])[0]
            self.assertEqual(artifact.sha256, hashlib.sha256(b"hello UNI").hexdigest())
            self.assertEqual(artifact.text_excerpt, "hello UNI")
            with self.assertRaisesRegex(ValueError, "escapes workspace"):
                ArtifactCollector(root).collect(["../outside.txt"])

    def test_paid_api_is_blocked_by_default(self):
        config = api_config("paid")
        config.api_cost = "paid"
        registry = ProviderRegistry([config])
        with self.assertRaisesRegex(PermissionError, "not allowed"):
            registry.build("paid")

    async def test_provider_sequence_creates_auditable_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "ADR.md"
            artifact.write_text("contract", encoding="utf-8")
            configs = [api_config("researcher"), api_config("critic")]
            coordinator = DevelopmentCoordinator(
                root,
                CoordinationStore(root / "state.json"),
                FakeRegistry(configs),
            )
            task = DevelopmentTask(
                title="Review",
                goal="Review the contract",
                instructions="Return findings only",
                provider_sequence=["researcher", "critic"],
                artifact_paths=["ADR.md"],
            )
            coordinator.create_task(task)
            result = await coordinator.run_all(task.id)
            self.assertEqual(result.status, TaskStatus.AWAITING_REVIEW)
            self.assertEqual(
                [item.provider_id for item in result.results], ["researcher", "critic"]
            )
            self.assertIn("previous=1", result.results[-1].content)
            self.assertEqual(
                [event.event for event in coordinator.store.events_for(task.id)],
                [
                    "task.created",
                    "provider.started",
                    "provider.completed",
                    "provider.started",
                    "provider.completed",
                ],
            )

    def test_duplicate_sequence_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "duplicates"):
            DevelopmentTask(
                title="Bad",
                goal="Bad sequence",
                instructions="Reject",
                provider_sequence=["critic", "critic"],
            )

    def test_dynamic_routing_prefers_low_priority_number(self):
        slower = api_config("slower")
        slower.priority = 50
        slower.capabilities = ["review"]
        preferred = api_config("preferred")
        preferred.priority = 10
        preferred.capabilities = ["review"]
        registry = ProviderRegistry([slower, preferred])
        self.assertEqual(registry.select(["review"], 2), ["preferred", "slower"])


if __name__ == "__main__":
    unittest.main()
