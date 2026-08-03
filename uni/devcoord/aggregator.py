"""
Aggregator: deduplication + best-response selection + quality scoring.

Cache lives in a JSON file (not SQLite). The Knowledge Base is used only to
prioritise providers with a successful past (passed in by the caller).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import ProviderResult


class AggregatedResult(BaseModel):
    """Final result after aggregation."""

    task_id: str
    best_response: ProviderResult
    alternatives: list[ProviderResult] = Field(default_factory=list)
    duplicates_removed: int = 0
    confidence: float = 0.0


class ResponseCache:
    """JSON file cache for provider responses (kept out of SQLite by design)."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "responses.json"
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                self._data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    def _save(self) -> None:
        self.cache_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, task_id: str, provider: str) -> Optional[str]:
        return self._data.get(f"{task_id}:{provider}")

    def set(self, task_id: str, provider: str, response: str) -> None:
        self._data[f"{task_id}:{provider}"] = response
        self._save()


class Aggregator:
    """Dedup + confidence selection, with an optional quality-aware path."""

    def __init__(self, cache_dir: Path):
        self.cache = ResponseCache(cache_dir)

    def aggregate(
        self,
        task_id: str,
        results: list[ProviderResult],
        successful_providers: set[str] | None = None,
    ) -> AggregatedResult:
        """Aggregate provider answers.

        - Uses the cache (re-uses a stored response when present).
        - Bonuses providers with a successful past (+0.2 confidence).
        - Deduplicates by md5 of the response content.
        - Picks the best by confidence.
        """
        successful_providers = successful_providers or set()

        cached_results: list[ProviderResult] = []
        for result in results:
            cached = self.cache.get(task_id, result.provider_id)
            if cached:
                result.content = cached
            else:
                self.cache.set(task_id, result.provider_id, result.content)
            cached_results.append(result)

        if successful_providers:
            for result in cached_results:
                if result.provider_id in successful_providers:
                    result.confidence = min(1.0, result.confidence + 0.2)

        seen_hashes: set[str] = set()
        unique_results: list[ProviderResult] = []
        duplicates_removed = 0
        for result in cached_results:
            code_hash = hashlib.md5(result.content.encode("utf-8")).hexdigest()
            if code_hash not in seen_hashes:
                seen_hashes.add(code_hash)
                unique_results.append(result)
            else:
                duplicates_removed += 1

        if not unique_results:
            raise ValueError("No valid responses to aggregate")

        best = max(unique_results, key=lambda r: r.confidence)
        alternatives = [r for r in unique_results if r is not best]
        return AggregatedResult(
            task_id=task_id,
            best_response=best,
            alternatives=alternatives,
            duplicates_removed=duplicates_removed,
            confidence=best.confidence,
        )

    # -- quality-aware aggregation -----------------------------------------

    @staticmethod
    def score_response(
        result: ProviderResult,
        verified: bool,
        has_tests: bool,
        follows_architecture: bool,
    ) -> float:
        """Quality score (0.0-1.0) for a proposal.

        - verified (Verifier confirmed the claims): 0.4
        - has_tests (code is covered by tests):     0.3
        - follows_architecture (passes check):      0.3
        """
        score = 0.0
        if verified:
            score += 0.4
        if has_tests:
            score += 0.3
        if follows_architecture:
            score += 0.3
        return score

    def _has_tests_in_response(self, content: str) -> bool:
        lowered = content.lower()
        markers = (
            "def test_", "pytest", "import unittest", "assert ",
            "test_case", "test case",
        )
        return any(m in lowered for m in markers)

    def _check_architecture(self, content: str) -> bool:
        """Heuristic: does the proposal avoid importing one capability from another?

        A real ``check_architecture.py`` run would require the actual repo; here we
        only flag the specific anti-pattern the audit catches (capability importing
        another capability). Callers may override with a precise check.
        """
        return "from uni.capabilities." not in content.replace(
            "from uni.capabilities.base", ""
        )

    def aggregate_with_quality(
        self,
        task_id: str,
        results: list[ProviderResult],
        successful_providers: set[str] | None = None,
    ) -> AggregatedResult:
        """Aggregate by quality score rather than raw confidence."""
        scored: list[tuple[ProviderResult, float]] = []
        for result in results:
            score = self.score_response(
                result,
                verified=bool(result.verified and result.verified.verified),
                has_tests=self._has_tests_in_response(result.content),
                follows_architecture=self._check_architecture(result.content),
            )
            scored.append((result, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_result, best_score = scored[0]
        return AggregatedResult(
            task_id=task_id,
            best_response=best_result,
            alternatives=[r for r, _ in scored[1:]],
            duplicates_removed=0,
            confidence=best_score,
        )
