# Coordinated assignments for UNI

All participants must treat `C:\LLM\UNI\uni` as canonical and the model-specific
directories as read-only reference material. Do not implement another task while
performing the assigned one.

## Claude — Software Architect

Task: `CORE-001` and architectural preparation for `ROUTER-001`.

Read:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `BUILD_STATUS.md`
- `.uni-dev/tasks.yaml`
- root `uni/contracts.py`
- `Uni-Claude/uni/contracts.py`
- root, DeepSeek, and OpenCode registry/executor interfaces

Deliver:

1. `docs/decisions/ADR-0004-runtime-contracts.md`.
2. A precise schema and ownership rules for `Action`, `ActionResult`,
   `Observation`, `AgentContext`, and `Task`.
3. A decision about async boundaries and exception-to-result conversion.
4. A short compatibility table showing how each current variant maps to the
   proposed contracts.
5. A draft decision for capability manifests and routing. Do not write runtime
   Python code.

Do not redesign the product or add frameworks.

## DeepSeek — Algorithms Engineer

Task: prepare `PLAN-001`; do not modify Python yet.

Read accepted contract and router ADRs first. If they are not accepted, report
the exact missing decisions and stop.

Deliver `docs/specs/planner-algorithm.md` containing:

1. Stable LLM-visible step IDs and deterministic mapping to `Task.id`.
2. JSON plan validation against capability manifests.
3. Ready-task selection with priorities and dependencies.
4. Error classification, bounded retry with backoff, replan, and ask-user rules.
5. Termination conditions for every loop.
6. Pseudocode and a state-transition table.
7. Test vectors for success, transient failure, permanent failure, invalid plan,
   dependency deadlock, exhausted replans, and user escalation.

Minimize LLM calls and do not create new architecture.

## Qwen — Python Module Developer

Task: `CORE-002`, but only after `ADR-0004` is accepted.

Allowed changes:

- `uni/contracts.py`
- `tests/unit/test_contracts.py`

Deliver:

1. Typed implementations of the accepted runtime contracts.
2. Validation of action names and bounded fields where required by the ADR.
3. Unit tests for valid construction, invalid values, serialization, timeout,
   failure, and verification results.
4. A compatibility note listing every existing module that will require a later
   adapter. Do not edit those modules.

Run:

```powershell
py -3 -m compileall -q uni tests
py -3 scripts/check_architecture.py
```

Do not implement the router, planner, or event loop.

## OpenCode + Nemotron — Lead Implementation Engineer

Task: inventory and integration plan now; implementation starts only after
`CORE-002`, `ROUTER-001`, and `PLAN-001` are accepted.

First deliver a written integration plan comparing:

- root `uni/event_loop.py`
- `Uni-DeepSeek/uni/event_loop.py`
- `Uni-OpenCode/uni/event_loop.py`
- corresponding agents, registries, executors, and working memories

The plan must specify what is retained, adapted, or rejected and why. Never copy
an entire variant over the canonical package.

After dependencies are accepted, implement `INTEGRATE-001` only within its
allowed paths. Required tests:

1. Successful multi-action plan.
2. One transient error followed by successful retry.
3. Permanent error followed by replan.
4. Invalid or unknown action rejected before execution.
5. Dependency deadlock detected.
6. Exhausted replans pause and request user help.
7. Empty goal/queue does not spin.

Every execution path must return the canonical `ActionResult`.
