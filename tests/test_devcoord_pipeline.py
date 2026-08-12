"""Tests for DevCoord aggregator, pipeline, and council bridge.

Run:
    PYTHONPATH=C:\\LLM\\UNI C:\\LLM\\python312\\python.exe -m pytest tests/test_devcoord_pipeline.py -q
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from uni.devcoord.aggregator import Aggregator, AggregatedResult
from uni.devcoord.coordinator import DevelopmentCoordinator
from uni.devcoord.council_bridge import CouncilBridge
from uni.devcoord.models import (
    DevelopmentTask,
    ProviderConfig,
    ProviderResult,
    TaskStatus,
)
from uni.devcoord.pipeline import DevPipeline, PipelineResult
from uni.devcoord.providers import ProviderRegistry
from uni.devcoord.verifier import Verifier
from uni.devcoord.applier import Applier, ApplyResult
from uni.devcoord.store import CoordinationStore
from uni.knowledge.base import CouncilResponse, KnowledgeBase


# --------------------------------------------------------------------------- #
# Aggregator
# --------------------------------------------------------------------------- #
def _result(provider_id: str, content: str, confidence: float = 0.5) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id, transport="api", content=content, confidence=confidence
    )


def test_aggregator_deduplicates_by_hash(tmp_path: Path):
    agg = Aggregator(tmp_path)
    # Three distinct contents -> no duplicates removed; all three present.
    results = [
        _result("a", "code A"),
        _result("b", "code B"),
        _result("c", "code C"),
    ]
    out = agg.aggregate("T1", results)
    assert isinstance(out, AggregatedResult)
    assert out.duplicates_removed == 0
    ids = {out.best_response.provider_id, *(r.provider_id for r in out.alternatives)}
    assert ids == {"a", "b", "c"}


def test_aggregator_deduplicates_same_content(tmp_path: Path):
    agg = Aggregator(tmp_path)
    # Two identical contents -> one duplicate removed; best chosen by confidence.
    results = [
        _result("a", "same code", confidence=0.2),
        _result("b", "same code", confidence=0.9),
        _result("c", "other", confidence=0.5),
    ]
    out = agg.aggregate("T1", results)
    assert out.duplicates_removed == 1
    # 'a' is kept as the first occurrence of the duplicate pair; among the
    # unique results [a(0.2), c(0.5)] the highest confidence is 'c'.
    assert out.best_response.provider_id == "c"
    # 'b' was deduplicated (same content as 'a'), so it is absent.
    ids = {out.best_response.provider_id, *(r.provider_id for r in out.alternatives)}
    assert ids == {"a", "c"}


def test_aggregator_uses_cache(tmp_path: Path):
    agg = Aggregator(tmp_path)
    first = agg.aggregate("T1", [_result("a", "hello")])
    # Second run with different content for provider "a" should be ignored
    # because the cache returns the stored "hello".
    second = agg.aggregate("T1", [_result("a", "IGNORED-DIFFERENT")])
    assert second.best_response.content == "hello"
    assert first.best_response.content == "hello"


def test_aggregator_bonuses_successful_providers(tmp_path: Path):
    agg = Aggregator(tmp_path)
    results = [
        _result("low", "code A", confidence=0.4),
        _result("high", "code B", confidence=0.4),
    ]
    out = agg.aggregate("T1", results, successful_providers={"high"})
    assert out.best_response.provider_id == "high"
    assert out.confidence == pytest.approx(0.6)


def test_aggregator_quality_picks_verified_with_tests(tmp_path: Path):
    agg = Aggregator(tmp_path)
    verified_with_tests = _result("a", "def test_x():\n    assert True\npatch", confidence=0.1)
    verified_with_tests.verified = type(
        "C", (), {"verified": True, "evidence": "ok", "claim": "", "checked_at": ""}
    )()
    weak = _result("b", "no tests here", confidence=0.9)
    out = agg.aggregate_with_quality("T1", [verified_with_tests, weak])
    assert out.best_response.provider_id == "a"
    # Clean content (no capability->capability import) scores full: 0.4 + 0.3 + 0.3.
    assert out.confidence == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Coordinator.select_participants
# --------------------------------------------------------------------------- #
def _make_coordinator(tmp_path: Path, kb: KnowledgeBase | None) -> DevelopmentCoordinator:
    store = CoordinationStore(tmp_path / "coord.json")
    cfgs = [
        ProviderConfig(
            id="free_p", display_name="free", transport="api", enabled=True,
            base_url="http://x/v1", model="m", api_cost="free",
        ),
        ProviderConfig(
            id="paid_p", display_name="paid", transport="api", enabled=True,
            base_url="http://x/v1", model="m", api_cost="paid",
        ),
    ]
    reg = ProviderRegistry(cfgs, allow_paid_api=True)
    return DevelopmentCoordinator(
        workspace=tmp_path, store=store, providers=reg, kb=kb,
        prompts_dir=Path(__file__).resolve().parents[1] / "uni" / "prompts",
    )


def test_select_participants_respects_budget(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    coord = _make_coordinator(tmp_path, kb)
    task = DevelopmentTask(
        title="add retry logic", goal="g", instructions="i",
        provider_sequence=["free_p", "paid_p"],
    )
    # budget 0 -> only the free provider survives.
    chosen = coord.select_participants(task, budget=0.0, max_participants=3)
    assert chosen == ["free_p"]


def test_select_participants_uses_kb_success(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    # Seed a successful past use of "paid_p" for a similar topic (verified).
    kb.store_response(
        CouncilResponse(
            response_id="old", task_id="old", provider="paid_p",
            topic="add retry logic", response_text="tenacity retry", confidence=0.6,
            used_in_patch=True, patch_success=True, verified=True,
        )
    )
    coord = _make_coordinator(tmp_path, kb)
    task = DevelopmentTask(
        title="add retry logic", goal="g", instructions="i",
        provider_sequence=["free_p", "paid_p"],
    )
    chosen = coord.select_participants(task, budget=None, max_participants=3)
    # paid_p has a successful history -> ranks first.
    assert chosen[0] == "paid_p"


def test_coordinator_loads_advisor_prompt(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    coord = _make_coordinator(tmp_path, kb)
    assert "Советник" in coord.advisor_prompt


# --------------------------------------------------------------------------- #
# Pipeline (stubbed coordinator / verifier / applier / kb)
# --------------------------------------------------------------------------- #
class _FakeVerifier:
    def verify_claim(self, claim, file_hint=None):
        from uni.devcoord.models import ClaimVerificationResult

        return ClaimVerificationResult(
            claim=claim, verified=True, evidence="stub", checked_at="now"
        )


class _FakeProvider:
    def __init__(self, provider_id: str, content: str):
        self.provider_id = provider_id
        self.content = content

    async def request(self, handoff):
        return ProviderResult(
            provider_id=self.provider_id, transport="api", content=self.content
        )


class _FakeCoordinator:
    def __init__(self, results: list[ProviderResult]):
        self._results = results
        self.verifier = _FakeVerifier()

    async def run_all(self, task_id: str) -> DevelopmentTask:
        task = DevelopmentTask(
            id=task_id, title="t", goal="g", instructions="i",
            provider_sequence=[r.provider_id for r in self._results],
        )
        task.results = self._results
        return task


class _FakeApplier:
    def __init__(self, status: str = "awaiting_human_confirmation"):
        self._status = status
        self.applied_task: str | None = None
        self.applied_patch: str | None = None

    async def apply_and_test(self, task_id: str, patch: str) -> ApplyResult:
        self.applied_task = task_id
        self.applied_patch = patch
        return ApplyResult(
            branch=f"review/{task_id}", diff="", tests_passed=True,
            test_output="ok", status=self._status,
        )


@pytest.mark.asyncio
async def test_pipeline_stores_responses_in_kb(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    results = [
        _result("groq", "add retry via tenacity"),
        _result("claude", "add retry using structlog"),
    ]
    # Mark one as verified (coordinator would do this via verifier).
    results[0].verified = type(
        "C", (), {"verified": True, "evidence": "e", "claim": "c", "checked_at": ""}
    )()
    coord = _FakeCoordinator(results)
    agg = Aggregator(tmp_path / "agg")
    applier = _FakeApplier(status="awaiting_human_confirmation")
    pipe = DevPipeline(coord, coord.verifier, agg, applier, kb)

    task = DevelopmentTask(
        id="DEV-1", title="add retry", goal="g", instructions="i",
        provider_sequence=["groq", "claude"],
    )
    out = await pipe.process_task(task)

    assert isinstance(out, PipelineResult)
    assert out.verified is True
    stored = kb.find_similar_responses("add retry", limit=10)
    # find_similar_responses returns verified rows only -> the one verified response.
    assert len(stored) == 1
    assert stored[0].provider == "groq"
    verified_stored = [r for r in stored if r.verified]
    assert len(verified_stored) == 1
    # Applier received the best (verified, highest-confidence) response content.
    assert applier.applied_patch == "add retry via tenacity"


@pytest.mark.asyncio
async def test_pipeline_uses_similar_responses(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    # Past success for "groq" on similar topic.
    kb.store_response(
        CouncilResponse(
            response_id="old", task_id="old", provider="groq", topic="add retry",
            response_text="past", confidence=0.5, used_in_patch=True, patch_success=True,
        )
    )
    results = [
        _result("groq", "add retry with tenacity", confidence=0.3),
        _result("claude", "add retry with structlog", confidence=0.3),
    ]
    for r in results:
        r.verified = type(
            "C", (), {"verified": True, "evidence": "e", "claim": "c", "checked_at": ""}
        )()
    coord = _FakeCoordinator(results)
    agg = Aggregator(tmp_path / "agg")
    applier = _FakeApplier(status="awaiting_human_confirmation")
    pipe = DevPipeline(coord, coord.verifier, agg, applier, kb)

    task = DevelopmentTask(
        id="DEV-2", title="add retry", goal="g", instructions="i",
        provider_sequence=["groq", "claude"],
    )
    out = await pipe.process_task(task)
    # groq gets +0.2 bonus -> chosen as best.
    assert out.aggregated.best_response.provider_id == "groq"


@pytest.mark.asyncio
async def test_pipeline_fails_without_verified(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    results = [_result("groq", "unverified proposal")]
    # Not verified -> pipeline should short-circuit.
    coord = _FakeCoordinator(results)
    agg = Aggregator(tmp_path / "agg")
    applier = _FakeApplier()
    pipe = DevPipeline(coord, coord.verifier, agg, applier, kb)
    task = DevelopmentTask(
        id="DEV-3", title="x", goal="g", instructions="i", provider_sequence=["groq"]
    )
    out = await pipe.process_task(task)
    assert out.status == "failed_no_verified_responses"
    assert applier.applied_task is None


# --------------------------------------------------------------------------- #
# CouncilBridge
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_council_bridge_creates_task(tmp_path: Path):
    kb = KnowledgeBase(tmp_path / "kb.db")
    results = [_result("groq", "def test_retry():\n    assert True", confidence=0.5)]
    results[0].verified = type(
        "C", (), {"verified": True, "evidence": "e", "claim": "c", "checked_at": ""}
    )()
    coord = _FakeCoordinator(results)
    agg = Aggregator(tmp_path / "agg")
    applier = _FakeApplier(status="awaiting_human_confirmation")
    pipe = DevPipeline(coord, coord.verifier, agg, applier, kb)

    tasks_dir = tmp_path / "tasks"
    bridge = CouncilBridge(pipe, tasks_dir, provider_sequence=["groq"])

    # Non-dev topic -> None.
    assert await bridge.handle_council_topic("hello world", "") is None

    # Dev topic -> PipelineResult and a persisted task file.
    out = await bridge.handle_council_topic("dev-task: add retry to brain", "brief")
    assert isinstance(out, PipelineResult)
    assert out.verified is True
    task_files = list(tasks_dir.glob("DEV-*.json"))
    assert len(task_files) == 1
