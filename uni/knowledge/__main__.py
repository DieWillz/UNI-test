"""CLI for the Knowledge Base.

Usage:
    python -m uni.knowledge list-skills
    python -m uni.knowledge search "retry pattern"
    python -m uni.knowledge export-skills > skills.md
"""
from __future__ import annotations

import sys
from pathlib import Path

from uni.knowledge.base import KnowledgeBase

DEFAULT_DB = Path(".uni-dev/knowledge.db")


def _open() -> KnowledgeBase:
    return KnowledgeBase(DEFAULT_DB)


def _cmd_list_skills() -> int:
    kb = _open()
    skills = kb.get_top_skills(limit=50)
    if not skills:
        print("(no skills yet)")
        return 0
    for s in skills:
        print(f"{s.skill_id}  x{s.success_count}  {s.name}")
        print(f"    {s.description}")
    return 0


def _cmd_search(query: str) -> int:
    kb = _open()
    hits = kb.find_similar_responses(query, limit=10)
    if not hits:
        print("(no matching responses)")
        return 0
    for r in hits:
        flag = "verified" if r.verified else "unverified"
        print(f"[{flag}] {r.provider} :: {r.topic}")
        print(f"    {r.response_text[:160]}")
    return 0


def _cmd_export_skills() -> int:
    kb = _open()
    skills = kb.get_top_skills(limit=200)
    print("# UNI Skills (exported from Knowledge Base)\n")
    if not skills:
        print("_No skills extracted yet._")
        return 0
    for s in skills:
        print(f"## {s.name} (`{s.skill_id}`)\n")
        print(f"- Successes: {s.success_count}  Failures: {s.failure_count}")
        print(f"- Description: {s.description}")
        print(f"- Source tasks: {', '.join(s.source_task_ids)}")
        if s.code_pattern:
            print("\n```")
            print(s.code_pattern)
            print("```\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__.strip())
        return 1
    cmd = argv[0]
    if cmd == "list-skills":
        return _cmd_list_skills()
    if cmd == "search":
        if len(argv) < 2:
            print("usage: python -m uni.knowledge search \"<query>\"")
            return 1
        return _cmd_search(" ".join(argv[1:]))
    if cmd == "export-skills":
        return _cmd_export_skills()
    print(f"unknown command: {cmd}")
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
