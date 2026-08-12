"""
DevPipeline: full auto-development loop with learning.

Counselor -> Verifier -> Aggregator -> Applier -> Knowledge Base
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import DevelopmentTask, ProviderResult
from .coordinator import DevelopmentCoordinator
from .verifier import Verifier
from .aggregator import Aggregator, AggregatedResult
from .applier import Applier, ApplyResult
from ..knowledge.base import KnowledgeBase, CouncilResponse


class PipelineResult(BaseModel):
    """Result of the full cycle."""

    task_id: str
    aggregated: Optional[AggregatedResult] = None
    verified: bool = False
    applied: Optional[ApplyResult] = None
    status: str = "pending"
    similar_responses: list[CouncilResponse] = Field(default_factory=list)


class DevPipeline:
    """Orchestrates the full auto-development cycle with learning.

    Flow:
    1. coordinator.run_all() — collect provider responses
    2. knowledge_base.store_response() — persist each response
    3. verifier — results already carry `verified` (set by the coordinator)
    4. knowledge_base.find_similar_responses() — past experience
    5. aggregator.aggregate() — pick the best (with past-success bonus)
    6. applier.apply_and_test() — review branch, tests, NO commit
    7. on success -> knowledge_base.mark_used_in_patch()
    """

    def __init__(
        self,
        coordinator: DevelopmentCoordinator,
        verifier: Verifier,
        aggregator: Aggregator,
        applier: Applier,
        knowledge_base: KnowledgeBase,
    ):
        self.coordinator = coordinator
        self.verifier = verifier
        self.aggregator = aggregator
        self.applier = applier
        self.kb = knowledge_base

    async def process_task(self, task: DevelopmentTask) -> PipelineResult:
        # 1. Collect provider responses (real coordinator API).
        task = await self.coordinator.run_all(task.id)
        results: list[ProviderResult] = task.results

        # 2. Persist every response for future learning.
        for result in results:
            self.kb.store_response(
                CouncilResponse(
                    response_id=f"{task.id}-{result.provider_id}",
                    task_id=task.id,
                    provider=result.provider_id,
                    topic=task.title,
                    response_text=result.content,
                    confidence=result.confidence,
                    verified=False,
                )
            )

        # 3. Past experience (knowledge base).
        similar = self.kb.find_similar_responses(task.title, limit=3)
        successful_providers = {
            r.provider for r in similar if r.used_in_patch and r.patch_success
        }

        # 4. Verified results (verifier ran inside the coordinator).
        verified_results = [
            r for r in results if r.verified and r.verified.verified
        ]
        for result in verified_results:
            self.kb.store_response(
                CouncilResponse(
                    response_id=f"{task.id}-{result.provider_id}",
                    task_id=task.id,
                    provider=result.provider_id,
                    topic=task.title,
                    response_text=result.content,
                    confidence=result.confidence,
                    verified=True,
                    verification_evidence=result.verified.evidence,
                )
            )

        if not verified_results:
            return PipelineResult(
                task_id=task.id,
                aggregated=None,
                verified=False,
                applied=None,
                status="failed_no_verified_responses",
                similar_responses=similar,
            )

        # 5. Aggregate (with past-success bonus).
        aggregated = self.aggregator.aggregate(
            task.id, verified_results, successful_providers=successful_providers
        )

        # 6. Apply the patch (never commits).
        applied = await self.applier.apply_and_test(
            task.id, aggregated.best_response.content
        )

        # 7. On success, mark the chosen response as used.
        if applied.status == "awaiting_human_confirmation":
            for result in verified_results:
                if result.provider_id == aggregated.best_response.provider_id:
                    self.kb.mark_used_in_patch(
                        f"{task.id}-{result.provider_id}", success=True
                    )

        return PipelineResult(
            task_id=task.id,
            aggregated=aggregated,
            verified=True,
            applied=applied,
            status=applied.status,
            similar_responses=similar,
        )
