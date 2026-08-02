# UNI Development Rules

This repository has one canonical product implementation: `C:\LLM\UNI\uni`.

`Uni-Claude`, `Uni-DeepSeek`, `Uni-OpenCode`, `Claude`, `backup`, `1`, and nested
copies are reference material only. Do not edit them and never import from them.

Before changing product code:

1. Read `ARCHITECTURE.md`, `BUILD_STATUS.md`, and accepted ADRs in
   `docs/decisions`.
2. Select one approved task from `.uni-dev/tasks.yaml`.
3. Change only the paths allowed by that task.
4. Do not change a public contract without an accepted ADR.
5. Run `py -3 scripts/check_architecture.py` and the task's acceptance tests.

Project invariants:

- Python executes; Markdown supplies knowledge; the LLM makes semantic decisions.
- Capabilities never import or call other capabilities directly.
- Planner knows capability manifests and actions, not concrete implementations.
- Every attempted action returns the canonical `ActionResult`.
- Canonical action names use `capability.action`, for example `browser.navigate`.
- Retry, timeout, and queue behavior are deterministic.
- Architectural disagreements become ADRs; they are not resolved silently in code.
- One task changes one bounded concern.
- No failing change is accepted into the canonical implementation.

If implementation reveals that an accepted contract cannot work, stop and create
a change request. Do not invent a local variation of that contract.
