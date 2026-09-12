# UNI Product Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a thin product-integration layer that makes existing UNI subsystems consumable as one product without duplicating execution authority.

**Architecture:** `uni/product_integration` contains only adapters, projections and read-only aggregation around canonical public contracts. Operator/DevCoord/WebUI/Telegram/Workspace/Checkpoints remain owners of their own behavior; cross-lane changes are requested via handoffs.

**Tech Stack:** Python 3.12, stdlib dataclasses/Protocol, existing `uni.contracts`, `uni.workspace`, `uni.checkpoints`, and transport models.

**Spec:** `docs/superpowers/specs/2026-09-12-uni-product-integration-design.md`

## Global Constraints

- Never create another brain, planner, executor, Operator or coordinator.
- Never synthesize runtime progress or task success.
- Owner verification and agent/test verification remain distinct.
- No writes to ACTIVE foreign lanes.
- No full pytest; targeted integration tests only.
### Task 1: Command lifecycle adapters

**Files:**
- Create: `uni/product_integration/models.py`
- Create: `uni/product_integration/lifecycle.py`
- Create: `uni/product_integration/__init__.py`
- Test: `tests/product_integration/test_lifecycle.py`

**Interfaces:**
- Consumes: `uni.contracts.TaskOutcome`, `TaskStatus`, `uni.transports.models.InboundMessage`.
- Produces: `ProductCommand`, `LifecycleEvent`, `LifecycleKind`, ingress helpers, final-outcome projection, best-effort TTS delivery result.

- [ ] Write RED tests proving text/Telegram/voice normalize to one command shape, acknowledgement is receipt-only, final status follows `TaskOutcome`, and TTS failure cannot change execution status.
- [ ] Run `python -m pytest tests/product_integration/test_lifecycle.py -q` and confirm failure because the package is absent.
- [ ] Implement only the adapter/projection behavior; no planner/executor logic.
- [ ] Re-run the same test file to GREEN.
### Task 2: Workspace source adapters and partial-failure facade

**Files:**
- Create: `uni/product_integration/workspace_adapters.py`
- Test: `tests/product_integration/test_workspace_adapters.py`

**Interfaces:**
- Consumes: a callable returning the existing `DevelopmentCoordinatorService.development_status()` dictionary; existing `WorkspaceService` and workspace view models.
- Produces: DevCoord-backed `AgentSource`/`TaskSource`, resilient source wrappers, `WorkspaceProductSnapshot` with `overview` plus per-source health.

- [ ] Write RED tests mapping sessions/tasks/leases into normalized workspace views without fake 100% progress.
- [ ] Add RED tests where agent/task/revision sources fail independently and the remaining overview still renders.
- [ ] Implement adapters without importing or mutating DevCoord implementation objects.
- [ ] Run only `tests/product_integration/test_workspace_adapters.py` to GREEN.
### Task 3: Checkpoint read-only integration

**Files:**
- Create: `uni/product_integration/checkpoint_adapters.py`
- Test: `tests/product_integration/test_checkpoint_adapters.py`

**Interfaces:**
- Consumes: public `CheckpointManager.list_checkpoints()`, `inspect_checkpoint()`, `prepare_restore()` and GitBackend read methods.
- Produces: Workspace `CheckpointView` source plus JSON-safe inspect/restore projections.

- [ ] Write RED tests for checkpoint mapping, current Project Known Good detection, inspect and prepare-restore projection.
- [ ] Prove adapter exposes no create-project or destructive activation operation.
- [ ] Implement using only public CheckpointManager methods and read-only Git state.
- [ ] Run the targeted checkpoint adapter tests to GREEN.
### Task 4: Product acceptance matrix

**Files:**
- Create: `uni/product_integration/acceptance.py`
- Test: `tests/product_integration/test_acceptance.py`

**Interfaces:**
- Produces: immutable acceptance rows for every required user scenario, with explicit current path, expected path, blocker, owner and test status.

- [ ] Write RED tests requiring all 13 owner-specified scenarios and rejecting missing/duplicate rows.
- [ ] Require explicit evidence before a row can be marked VERIFIED.
- [ ] Implement the matrix model and JSON/table projection without inventing test status.
- [ ] Run the targeted acceptance tests to GREEN.

### Task 5: Read-only cross-lane audit and handoffs

**Files:**
- Create: `docs/handoffs/UNI_PRODUCT_INTEGRATION_OPERATOR_REQUEST.md`
- Create: `docs/handoffs/UNI_PRODUCT_INTEGRATION_WEBUI_REQUEST.md`
- Create: `docs/handoffs/UNI_PRODUCT_INTEGRATION_HERMES_REQUEST.md`

- [ ] Inspect only the relevant WebUI settings/admin/workspace files and Hermes/Operator public seams.
- [ ] Record exact owner-lane requests for typed Operator progress/replan events, WebUI safe navigation/settings persistence, and Telegram binding to the common command port.
- [ ] Do not edit the foreign production/test files.
### Task 6: Final integration result and verification

**Files:**
- Create: `docs/handoffs/UNI_PRODUCT_INTEGRATION_RESULT.md`

- [ ] Run `python -m pytest tests/product_integration -q` only.
- [ ] Run `python -m compileall -q uni/product_integration tests/product_integration`.
- [ ] Run `python scripts/check_verification_invariant.py`.
- [ ] Run `python -m uni.check_architecture --strict` if it does not require touching foreign state.
- [ ] Run `git diff --check` limited to owned Product Integration paths/docs.
- [ ] Record scenario matrix with VERIFIED / NOT_VERIFIED / BLOCKED based only on fresh evidence.
- [ ] Finish the handoff using the required sections: STATUS, USER SCENARIOS WORKING, USER SCENARIOS BLOCKED, INTEGRATED INPUTS, WEBUI STATUS, WORKSPACE STATUS, KNOWN GOOD STATUS, OPERATOR HANDOFF REQUESTS, TESTED, NOT_VERIFIED, NEXT.

## Plan self-review

Coverage: lifecycle, voice/TTS safety, Telegram seam, Workspace/Checkpoint adapters, partial failure, Known Good read-only operations, acceptance matrix, safe admin/settings handoffs, and targeted verification are all represented.
No foreign ACTIVE lane is scheduled for modification.
All success claims require canonical verification evidence.