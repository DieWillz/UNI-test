from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from uni.devcoord.config import load_development_config
from uni.devcoord.coordinator import DevelopmentCoordinator
from uni.devcoord.models import DevelopmentTask
from uni.devcoord.providers import ProviderRegistry
from uni.devcoord.store import CoordinationStore


def build_coordinator(workspace: Path, config_path: Path) -> DevelopmentCoordinator:
    config = load_development_config(config_path)
    state_path = (workspace / config.state_path).resolve()
    return DevelopmentCoordinator(
        workspace,
        CoordinationStore(state_path),
        ProviderRegistry(config.providers, allow_paid_api=config.allow_paid_api),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="UNI development coordination layer")
    result.add_argument("--workspace", default=".")
    result.add_argument("--config", default=".uni-dev/coordination/providers.example.yaml")
    sub = result.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create a development task")
    create.add_argument("--title", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--instructions", required=True)
    create.add_argument("--providers", default="", help="comma-separated provider ids")
    create.add_argument("--capability", action="append", default=[])
    create.add_argument("--provider-count", type=int, default=1)
    create.add_argument("--continue-on-error", action="store_true")
    create.add_argument("--file", action="append", default=[])
    create.add_argument("--constraint", action="append", default=[])
    create.add_argument("--expected-output", default="Structured review and recommendations")
    sub.add_parser("list", help="list tasks")
    show = sub.add_parser("show", help="show task and events")
    show.add_argument("task_id")
    run = sub.add_parser("run", help="run all remaining providers")
    run.add_argument("task_id")
    return result


async def main() -> int:
    args = parser().parse_args()
    workspace = Path(args.workspace).resolve()
    coordinator = build_coordinator(workspace, (workspace / args.config).resolve())
    if args.command == "create":
        task = DevelopmentTask(
            title=args.title,
            goal=args.goal,
            instructions=args.instructions,
            provider_sequence=[value.strip() for value in args.providers.split(",") if value.strip()],
            required_capabilities=args.capability,
            requested_provider_count=args.provider_count,
            continue_on_error=args.continue_on_error,
            artifact_paths=args.file,
            constraints=args.constraint,
            expected_output=args.expected_output,
        )
        coordinator.create_task(task)
        print(task.id)
    elif args.command == "list":
        for task in coordinator.store.list_tasks():
            print(f"{task.id}\t{task.status.value}\t{task.title}")
    elif args.command == "show":
        task = coordinator.store.get_task(args.task_id)
        payload = task.model_dump(mode="json")
        payload["events"] = [event.model_dump(mode="json") for event in coordinator.store.events_for(task.id)]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.command == "run":
        task = await coordinator.run_all(args.task_id)
        print(json.dumps(task.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
