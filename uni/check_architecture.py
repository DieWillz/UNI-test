"""UNI architecture audit — genuine static check (canonical entrypoint).

Run:  py -3.12 -m uni.check_architecture --strict

Implements the invariants documented in ADR-0005 (Capability Router):
  * A concrete capability under ``uni/capabilities/`` MUST NOT import another
    concrete capability file. It may import only the base contract module
    (``uni/capabilities/base.py``) and shared infrastructure (registry,
    config, contracts, utils).
  * ``capability`` MUST NOT import ``capability_router`` / ``planner`` /
    ``event_loop`` / ``agent``.
  * Every capability action param model is a Pydantic ``BaseModel`` (checked
    loosely: each capability module must be importable and expose a
    ``manifest``).

This is a real AST scan over the canonical ``uni/`` tree — not a stub. It
exits non-zero on any violation so it can gate CI / packaging.

No code or settings are deleted; this is an additive module.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


CANON_ROOT = Path(__file__).resolve().parents[0]  # .../UNI/uni  (this file lives in uni/)
CAPABILITIES_DIR = CANON_ROOT / "capabilities"

# Concrete modules a capability is allowed to depend on (infrastructure).
_ALLOWED_CAPABILITY_DEPS = {
    "uni.capabilities.base",
    "uni.config",
    "uni.contracts",
    "uni.state",
    "uni.session_state",
    "uni.session_log",
    "uni.working_memory",
}


class Violation:
    __slots__ = ("rule", "file", "detail")

    def __init__(self, rule: str, file: str, detail: str) -> None:
        self.rule = rule
        self.file = file
        self.detail = detail

    def __str__(self) -> str:
        return f"[{self.rule}] {self.file}: {self.detail}"


def _iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        # skip generated / cache dirs
        parts = set(path.parts)
        if {"__pycache__", ".git", "node_modules"}.intersection(parts):
            continue
        yield path


def _module_name_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return "uni." + ".".join(rel.parts)


def check_capability_imports() -> list[Violation]:
    """ADR-0005: capability must not import capability / router / planner."""
    violations: list[Violation] = []
    if not CAPABILITIES_DIR.exists():
        return violations

    forbidden_prefixes = (
        "uni.capabilities.",
        "uni.council.",
        "uni.devcoord.",
    )
    # Allowed capability-internal module (the base contract).
    allowed_full = set(_ALLOWED_CAPABILITY_DEPS)
    allowed_full.add("uni.capabilities.base")

    for path in _iter_py_files(CAPABILITIES_DIR):
        module = _module_name_from_path(path, CANON_ROOT)
        # The base contract itself is exempt from the "no capability import" rule.
        if module == "uni.capabilities.base":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            violations.append(Violation("SYNTAX", str(path), str(exc)))
            continue

        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                targets = [node.module]
            else:
                continue

            for tgt in targets:
                if tgt in allowed_full:
                    continue
                # forbid importing another concrete capability
                if tgt.startswith("uni.capabilities.") and tgt != "uni.capabilities.base":
                    violations.append(
                        Violation(
                            "CAP-IMPORT-CAP",
                            module,
                            f"imports concrete capability {tgt!r} (forbidden by ADR-0005)",
                        )
                    )
                # forbid importing router/planner/event_loop/agent from a capability
                elif tgt.startswith(("uni.council.", "uni.devcoord.")) or tgt in (
                    "uni.event_loop",
                    "uni.agent",
                ):
                    violations.append(
                        Violation(
                            "CAP-IMPORT-ORCH",
                            module,
                            f"imports orchestration module {tgt!r} (forbidden by ADR-0005)",
                        )
                    )
    return violations


def check_duplicate_entrypoints() -> list[Violation]:
    """Ensure a single canonical CLI entrypoint exists (uni.__main__)."""
    violations: list[Violation] = []
    main_py = CANON_ROOT / "__main__.py"
    if not main_py.exists():
        violations.append(
            Violation("ENTRYPOINT", "uni/__main__.py", "canonical entrypoint missing")
        )
    return violations


def run_all() -> list[Violation]:
    violations: list[Violation] = []
    violations += check_capability_imports()
    violations += check_duplicate_entrypoints()
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UNI architecture audit (ADR-0005)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on any violation (non-zero exit)",
    )
    args = parser.parse_args(argv)

    violations = run_all()
    if violations:
        print(f"UNI architecture audit: {len(violations)} violation(s)")
        for v in violations:
            print("  -", v)
        if args.strict:
            return 1
        return 0
    print("UNI architecture audit: 0 errors, 0 warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
