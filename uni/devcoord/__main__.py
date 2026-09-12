"""CLI for DevCoord and the live Multi-Agent Workspace Coordinator."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from uni.direction_sync import DirectionSyncGate
from uni.devcoord.applier import Applier
from uni.devcoord.direction_gate import MawcDirectionCoordinator
from uni.devcoord.service import DevelopmentCoordinatorService
from uni.devcoord.workspace_store import WorkspaceStore

_DEFAULT_DB = ".uni-dev/coordination/workspace.sqlite"


def _add_db_argument(
    parser: argparse.ArgumentParser, *, default: str | object = _DEFAULT_DB
) -> None:
    parser.add_argument(
        "--db",
        default=default,
        help=f"MAWC SQLite database (default: {_DEFAULT_DB}).",
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _emit(value: Any) -> None:
    print(json.dumps(_jsonable(value), ensure_ascii=False, indent=2))


def _service(
    db_path: str, *, repo_root: str | Path | None = None
) -> DevelopmentCoordinatorService:
    db = Path(db_path).resolve()
    store = WorkspaceStore(db)
    root: Path | None = None
    if repo_root is not None:
        root = Path(repo_root).resolve()
    elif db.parent.name == "coordination" and db.parent.parent.name == ".uni-dev":
        root = db.parent.parent.parent
    if root is None:
        return DevelopmentCoordinatorService(store)
    gate = DirectionSyncGate(
        root / "docs" / "handoffs" / "UNI_MASTER_DIRECTION.md",
        root / "docs" / "handoffs" / "UNI_ACTIVE_WORK.md",
        root / ".uni-dev" / "coordination" / "direction_ack.json",
    )
    return DevelopmentCoordinatorService(
        store, direction_sync=MawcDirectionCoordinator(store, gate)
    )


def _workspace_parser(sub, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help_text)
    _add_db_argument(parser, default=argparse.SUPPRESS)
    return parser


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UNI Development Coordinator CLI")
    _add_db_argument(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    confirm = sub.add_parser("confirm", help="Merge a review/<task_id> branch")
    confirm.add_argument("task_id")
    confirm.add_argument("--repo", default=".", help="Repository root.")

    for name, help_text in (
        ("status", "Show complete MAWC status"),
        ("agents", "List registered agent sessions"),
        ("tasks", "List workspace tasks"),
        ("leases", "List active resource leases"),
        ("conflicts", "List recent conflict events"),
    ):
        _workspace_parser(sub, name, help_text)

    owner = _workspace_parser(sub, "file-owner", "Show active owner of a file")
    owner.add_argument("path")

    pause_agent = _workspace_parser(sub, "pause-agent", "Pause an idle agent session")
    pause_agent.add_argument("agent")
    resume_agent = _workspace_parser(sub, "resume-agent", "Resume an agent session")
    resume_agent.add_argument("agent")

    prioritize = _workspace_parser(sub, "prioritize-task", "Change task priority")
    prioritize.add_argument("task_id")
    prioritize.add_argument("priority", type=int)
    pause_task = _workspace_parser(sub, "pause-task", "Pause a queued task")
    pause_task.add_argument("task_id")
    resume_task = _workspace_parser(sub, "resume-task", "Resume a blocked task")
    resume_task.add_argument("task_id")

    inspect_agent = _workspace_parser(sub, "inspect-agent", "Inspect one agent session")
    inspect_agent.add_argument("agent")
    inspect_task = _workspace_parser(sub, "inspect-task", "Inspect one workspace task")
    inspect_task.add_argument("task_id")

    assign_task = _workspace_parser(sub, "assign-task", "Assign an eligible task to a session")
    assign_task.add_argument("task_id")
    assign_task.add_argument("session_id")
    assign_task.add_argument("--ttl", type=float, default=600.0)
    assign_next = _workspace_parser(sub, "assign-next", "Assign the next eligible task")
    assign_next.add_argument("session_id")
    assign_next.add_argument("--ttl", type=float, default=600.0)

    ack_direction = _workspace_parser(
        sub, "ack-direction", "Acknowledge the current project direction revision"
    )
    ack_direction.add_argument("session_id")

    heartbeat = _workspace_parser(sub, "heartbeat", "Refresh an agent session heartbeat")
    heartbeat.add_argument("session_id")
    heartbeat.add_argument("--ttl", type=float, default=600.0)
    can_write = _workspace_parser(sub, "can-write", "Check whether an agent may edit a path")
    can_write.add_argument("agent")
    can_write.add_argument("path")
    audit = _workspace_parser(sub, "audit", "Audit changed paths against active leases")
    audit.add_argument("paths", nargs="+")
    audit.add_argument("--session", dest="expected_session_id")
    release = _workspace_parser(sub, "release-lease", "Release one resource lease")
    release.add_argument("lease_id")
    stop_agent = _workspace_parser(sub, "stop-agent", "Stop an idle agent session")
    stop_agent.add_argument("agent")
    takeover = _workspace_parser(sub, "force-takeover", "Take over a stale session")
    takeover.add_argument("session_id")
    takeover.add_argument("snapshot_ref")
    reassign = _workspace_parser(sub, "reassign-task", "Move a claimed task to another session")
    reassign.add_argument("task_id")
    reassign.add_argument("session_id")
    reassign.add_argument("--ttl", type=float, default=600.0)
    return parser


def _run_workspace_command(args: argparse.Namespace) -> int:
    service = _service(args.db)
    command = args.command
    if command == "status":
        _emit(service.development_status())
    elif command in {"agents", "tasks", "leases", "conflicts"}:
        _emit(service.development_status()[command])
    elif command == "file-owner":
        _emit(service.inspect_file_owner(args.path))
    elif command == "pause-agent":
        _emit(service.pause_agent(args.agent))
    elif command == "resume-agent":
        _emit(service.resume_agent(args.agent))
    elif command == "prioritize-task":
        _emit(service.prioritize_task(args.task_id, args.priority))
    elif command == "pause-task":
        _emit(service.pause_task(args.task_id))
    elif command == "resume-task":
        _emit(service.resume_task(args.task_id))
    elif command == "inspect-agent":
        _emit(service.inspect_agent(args.agent))
    elif command == "inspect-task":
        _emit(service.inspect_task(args.task_id))
    elif command == "assign-task":
        _emit(service.assign_task(args.task_id, args.session_id, ttl_seconds=args.ttl))
    elif command == "assign-next":
        _emit(service.assign_next(args.session_id, ttl_seconds=args.ttl))
    elif command == "ack-direction":
        _emit(service.acknowledge_direction(args.session_id))
    elif command == "heartbeat":
        _emit(service.heartbeat(args.session_id, ttl_seconds=args.ttl))
    elif command == "can-write":
        _emit(service.can_write(args.agent, args.path))
    elif command == "audit":
        _emit(service.audit_paths(args.paths, expected_session_id=args.expected_session_id))
    elif command == "release-lease":
        _emit(service.release_lease(args.lease_id))
    elif command == "stop-agent":
        _emit(service.stop_agent(args.agent))
    elif command == "force-takeover":
        _emit(service.force_takeover(args.session_id, args.snapshot_ref))
    elif command == "reassign-task":
        _emit(service.reassign_task(args.task_id, args.session_id, ttl_seconds=args.ttl))
    else:
        raise ValueError(f"unsupported workspace command: {command}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "confirm":
        repo_root = Path(args.repo).resolve()
        ok = asyncio.run(Applier(repo_root).confirm_merge(args.task_id))
        if ok:
            print(f"merged review/{args.task_id} into base branch")
            return 0
        print(f"confirm_merge failed for task {args.task_id} (branch may not exist)")
        return 1

    try:
        return _run_workspace_command(args)
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        _emit({"error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
