from __future__ import annotations

from pathlib import Path

from uni.devcoord.artifacts import ArtifactCollector
from uni.devcoord.models import (
    CoordinatorEvent,
    DevelopmentTask,
    HandoffPackage,
    TaskStatus,
    utc_now,
)
from uni.devcoord.providers import ProviderRegistry
from uni.devcoord.store import CoordinationStore
from uni.devcoord.verifier import Verifier
from uni.knowledge.base import KnowledgeBase


def _parse_cost(value: str | None) -> float:
    """Turn a ProviderConfig.api_cost string into a numeric cost estimate.

    'free' -> 0.0, 'unknown' -> 1.0 (treated as paid-but-unpriced), otherwise
    parse the leading float. Used only for budget filtering in select_participants.
    """
    if not value:
        return 1.0
    low = value.strip().lower()
    if low == "free":
        return 0.0
    if low in ("unknown", ""):
        return 1.0
    try:
        return float(low.split()[0])
    except ValueError:
        return 1.0


class DevelopmentCoordinator:
    def __init__(
        self,
        workspace: str | Path,
        store: CoordinationStore,
        providers: ProviderRegistry,
        verifier: Verifier | None = None,
        prompts_dir: str | Path | None = None,
        kb: KnowledgeBase | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.store = store
        self.providers = providers
        self.artifacts = ArtifactCollector(self.workspace)
        self.verifier = verifier
        self.kb = kb
        self.prompts_dir = Path(prompts_dir) if prompts_dir else None
        self.advisor_prompt = self._load_prompt("system_prompt_advisor.txt")
        self.critic_prompt = self._load_prompt("system_prompt_critic.txt")
        self.executor_prompt = self._load_prompt("system_prompt_executor.txt")

    def _load_prompt(self, name: str) -> str:
        if not self.prompts_dir:
            return ""
        path = self.prompts_dir / name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    # -- participant selection (priority selector) --------------------------
    def select_participants(
        self,
        task: DevelopmentTask,
        budget: float | None = None,
        max_participants: int = 3,
    ) -> list[str]:
        """Pick participants by past success (from KnowledgeBase) and cost.

        Steps:
        1. Gather past success stats per provider from the Knowledge Base.
        2. Confidence = successes / total past uses (0.5 fallback when no data).
        3. Filter by ``budget`` using the provider's parsed api_cost.
        4. Sort by confidence, return top-N provider ids.
        """
        provider_success: dict[str, dict[str, int]] = {}
        if self.kb is not None:
            similar = self.kb.find_similar_responses(task.title, limit=10)
            for r in similar:
                stats = provider_success.setdefault(r.provider, {"success": 0, "total": 0})
                stats["total"] += 1
                if r.used_in_patch and r.patch_success:
                    stats["success"] += 1

        candidates: list[tuple[str, float, float]] = []
        for cfg in self.providers.configs.values():
            stats = provider_success.get(cfg.id, {"success": 0, "total": 0})
            confidence = stats["success"] / max(stats["total"], 1)
            cost = _parse_cost(getattr(cfg, "api_cost", None))
            candidates.append((cfg.id, confidence, cost))

        if budget is not None:
            candidates = [c for c in candidates if c[2] <= budget]

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:max_participants]]

    def create_task(self, task: DevelopmentTask) -> DevelopmentTask:
        # Validate all artifacts before persisting the task.
        self.artifacts.collect(task.artifact_paths)
        if not task.provider_sequence:
            task.provider_sequence = self.providers.select(
                task.required_capabilities, task.requested_provider_count
            )
        self.store.save_task(task)
        self.store.append_event(
            CoordinatorEvent(event="task.created", task_id=task.id, detail=task.title)
        )
        return task

    async def run_next(self, task_id: str, verify_claim: str | None = None) -> DevelopmentTask:
        task = self.store.get_task(task_id)
        if task.next_provider_index >= len(task.provider_sequence):
            task.status = TaskStatus.AWAITING_REVIEW
            task.updated_at = utc_now()
            self.store.save_task(task)
            return task
        provider_id = task.provider_sequence[task.next_provider_index]
        provider = self.providers.build(provider_id)
        artifacts = self.artifacts.collect(task.artifact_paths)
        instructions = task.instructions
        if self.advisor_prompt:
            instructions = f"{self.advisor_prompt}\n\n{task.instructions}"
        handoff = HandoffPackage(
            task_id=task.id,
            goal=task.goal,
            instructions=instructions,
            from_agent=(task.results[-1].provider_id if task.results else "coordinator"),
            to_agent=provider_id,
            context_summary=task.context_summary,
            constraints=task.constraints,
            artifacts=artifacts,
            previous_results=task.results,
            expected_output=task.expected_output,
        )
        task.status = TaskStatus.RUNNING
        task.updated_at = utc_now()
        self.store.save_task(task)
        self.store.append_event(
            CoordinatorEvent(event="provider.started", task_id=task.id, provider_id=provider_id)
        )
        result = await provider.request(handoff)
        if verify_claim and self.verifier is not None:
            result.verified = self.verifier.verify_claim(verify_claim)
        task.results.append(result)
        task.next_provider_index += 1
        task.status = (
            TaskStatus.FAILED
            if result.error and task.next_provider_index >= len(task.provider_sequence)
            else TaskStatus.AWAITING_REVIEW
            if task.next_provider_index >= len(task.provider_sequence)
            else TaskStatus.PENDING
        )
        task.updated_at = utc_now()
        self.store.save_task(task)
        self.store.append_event(
            CoordinatorEvent(
                event="provider.failed" if result.error else "provider.completed",
                task_id=task.id,
                provider_id=provider_id,
                detail=result.error or f"response chars: {len(result.content)}",
            )
        )
        return task

    async def run_all(self, task_id: str, verify_claim: str | None = None) -> DevelopmentTask:
        task = self.store.get_task(task_id)
        remaining = len(task.provider_sequence) - task.next_provider_index
        for _ in range(max(0, remaining)):
            task = await self.run_next(task_id, verify_claim=verify_claim)
            if task.results[-1].error and not task.continue_on_error:
                break
        return task
