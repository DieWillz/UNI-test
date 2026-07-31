"""Read-only architecture audit for the canonical UNI package."""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "uni"
ARCHIVE_NAMES = {
    "Uni-Claude",
    "Uni-DeepSeek",
    "Uni-OpenCode",
    "Claude",
    "backup",
}
CONTRACT_NAMES = {"Action", "ActionResult", "Observation", "AgentContext"}


def python_files() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
        and not (len(path.relative_to(PACKAGE).parts) > 1
                 and path.relative_to(PACKAGE).parts[0] == "uni")
    )


def imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def audit() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    definitions: dict[str, list[str]] = defaultdict(list)

    nested_package = PACKAGE / "uni"
    if nested_package.exists():
        warnings.append(
            "Nested canonical copy exists at uni/uni; it must remain unused "
            "until a dedicated cleanup task archives it."
        )

    for path in python_files():
        relative = path.relative_to(ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{relative}: cannot parse: {exc}")
            continue

        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in CONTRACT_NAMES:
                    definitions[node.name].append(str(relative))

        modules = imported_modules(tree)
        for module in modules:
            if any(name.lower().replace("-", "_") in module.lower()
                   for name in ARCHIVE_NAMES):
                errors.append(f"{relative}: imports archived implementation {module}")

        parts = relative.parts
        if "capabilities" in parts and path.name not in {"__init__.py", "registry.py"}:
            for module in modules:
                if ".capabilities." in module or module.startswith("uni.capabilities."):
                    target = module.rsplit(".", 1)[-1]
                    if target not in {"base", "registry"}:
                        errors.append(
                            f"{relative}: capability imports another capability: {module}"
                        )

    for name, locations in sorted(definitions.items()):
        if len(locations) > 1:
            errors.append(
                f"Canonical contract {name} has multiple definitions: "
                + ", ".join(locations)
            )

    executor = PACKAGE / "tools" / "executors.py"
    planner = PACKAGE / "planner.py"
    if executor.exists() and planner.exists():
        executor_text = executor.read_text(encoding="utf-8")
        planner_text = planner.read_text(encoding="utf-8")
        if '"browser_navigate"' in executor_text and "capability.action" in planner_text:
            errors.append(
                "Action naming mismatch: executor uses underscore names while "
                "planner requests capability.action."
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a failing exit code for architecture errors.",
    )
    args = parser.parse_args()
    errors, warnings = audit()

    print("UNI architecture audit")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)")

    return 1 if args.strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
