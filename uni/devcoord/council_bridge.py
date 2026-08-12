"""
Bridge between Council (dev-task topics) and DevCoord.

When a Council topic starts with "dev-task:", a DevelopmentTask is created and
handed to the DevPipeline. The live SSE wiring into server.py / uni/council/* is
out of scope (those files are protected); this module is the library + unit test.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from .models import DevelopmentTask
from .pipeline import DevPipeline, PipelineResult


class CouncilBridge:
    """Integration point Council -> DevCoord.

    Flow:
        Council topic "dev-task: add retry to brain.py"
            -> bridge.handle_council_topic()
            -> pipeline.process_task()
            -> Council reply: "Patch ready, diff + tests, awaiting confirmation"
            -> Human: `python -m uni.devcoord confirm <task_id>`
    """

    def __init__(
        self,
        pipeline: DevPipeline,
        tasks_dir: Path,
        provider_sequence: list[str] | None = None,
    ):
        self.pipeline = pipeline
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.provider_sequence = provider_sequence or []

    async def handle_council_topic(
        self, topic: str, brief: str
    ) -> Optional[PipelineResult]:
        """Handle a Council topic.

        Returns a PipelineResult when the topic starts with "dev-task:",
        otherwise None (not a dev task).
        """
        if not topic.startswith("dev-task:"):
            return None

        task_description = topic[len("dev-task:"):].strip()
        task = DevelopmentTask(
            id=f"DEV-{uuid.uuid4().hex[:8].upper()}",
            title=task_description,
            goal=task_description,
            instructions=f"{task_description}\n\n{brief}",
            provider_sequence=self.provider_sequence,
        )

        # Persist for inspection / resumption.
        task_file = self.tasks_dir / f"{task.id}.json"
        task_file.write_text(
            json.dumps(task.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return await self.pipeline.process_task(task)
