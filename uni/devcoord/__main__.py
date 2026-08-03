"""CLI for DevCoord.

Usage:
    python -m uni.devcoord confirm <task_id> [--repo DIR]

Merges the review/<task_id> branch into the base branch. This is the only
merge path and is intended to be run by a human after inspecting the diff and
test output produced by Applier.apply_and_test (which never commits/merges
automatically).
"""
from __future__ import annotations

import asyncio
import argparse
import sys
from pathlib import Path

from uni.devcoord.applier import Applier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DevCoord CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    confirm = sub.add_parser("confirm", help="Merge a review/<task_id> branch")
    confirm.add_argument("task_id")
    confirm.add_argument(
        "--repo", default=".",
        help="Repository root (default: current directory).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "confirm":
        repo_root = Path(args.repo).resolve()
        applier = Applier(repo_root)
        ok = asyncio.run(applier.confirm_merge(args.task_id))
        if ok:
            print(f"merged review/{args.task_id} into base branch")
            return 0
        print(f"confirm_merge failed for task {args.task_id} (branch may not exist)")
        return 1
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
