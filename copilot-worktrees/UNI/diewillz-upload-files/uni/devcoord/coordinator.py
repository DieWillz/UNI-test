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


class DevelopmentCoordinator:
    def __init__(
        self,
        workspace: str | Path,
        store: CoordinationStore,
        providers: ProviderRegistry,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.store = store
        self.providers = providers
        self.artifacts = ArtifactCollector(self.workspace)

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

    async def run_next(self, task_id: str) -> DevelopmentTask:
        task = self.store.get_task(task_id)
        if task.next_provider_index >= len(task.provider_sequence):
            task.status = TaskStatus.AWAITING_REVIEW
            task.updated_at = utc_now()
            self.store.save_task(task)
            return task
        provider_id = task.provider_sequence[task.next_provider_index]
        provider = self.providers.build(provider_id)
        artifacts = self.artifacts.collect(task.artifact_paths)
        handoff = HandoffPackage(
            task_id=task.id,
            goal=task.goal,
            instructions=task.instructions,
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

    async def run_all(self, task_id: str) -> DevelopmentTask:
        task = self.store.get_task(task_id)
        remaining = len(task.provider_sequence) - task.next_provider_index
        for _ in range(max(0, remaining)):
            task = await self.run_next(task_id)
            if task.results[-1].error and not task.continue_on_error:
                break
        return task
