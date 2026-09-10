# UNI MAWC Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a process-safe SQLite-backed multi-agent resource lease core to UNI without modifying the existing JSON `CoordinationStore` behavior.

**Architecture:** New MAWC modules live beside existing `uni.devcoord` orchestration. `WorkspaceStore` owns SQLite schema/transactions; pure resource overlap rules live in `lease_rules.py`; `ResourceLeaseManager` and `AgentSessionManager` expose the runtime API. Existing `DevelopmentCoordinator` remains unchanged in Phase 1.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-mawc-design.md`

## Global Constraints

- Work only in `uni/devcoord/**`, `tests/devcoord/**`, `.uni-dev/**`, and MAWC docs for this phase.
- Do not edit protected verification files.
- Do not replace or migrate `CoordinationStore` yet.
- All production behavior starts with a failing test.
- SQLite claims use `BEGIN IMMEDIATE` and are all-or-nothing.
- Dirty stale WRITE ownership is never auto-released.

---

### Task 1: MAWC domain models and schema

**Files:**
- Create: `uni/devcoord/workspace_models.py`
- Create: `uni/devcoord/workspace_store.py`
- Test: `tests/devcoord/test_workspace_store.py`

**Interfaces:**
- Produces `ResourceType`, `AccessMode`, `LeaseState`, `SessionState`, `ResourceRequest`, `ResourceLease`, `AgentSession`, `WorkspaceEvent`.
- Produces `WorkspaceStore(path)` with schema initialization and transaction helper.

- [ ] **Step 1: Write failing schema/store tests**

Test that a fresh store enables WAL/foreign keys, creates `agent_sessions`, `resource_leases`, and `workspace_events`, and can persist/query one session and event.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_workspace_store.py -q`
Expected: import/module failure because Phase 1 store does not exist yet.

- [ ] **Step 3: Implement minimal models and store**

Use Pydantic string enums/models. `WorkspaceStore` creates parent directories, connects with timeout, enables `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, and initializes versioned tables without touching `state.json`.

- [ ] **Step 4: Run focused test and existing devcoord regression**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_workspace_store.py tests/devcoord/test_development_coordinator.py -q`
Expected: PASS.

### Task 2: Atomic resource claims and conflict rules

**Files:**
- Create: `uni/devcoord/lease_rules.py`
- Create: `uni/devcoord/leases.py`
- Test: `tests/devcoord/test_resource_leases.py`

**Interfaces:**
- `resources_overlap(a_type, a_key, b_type, b_key) -> bool`
- `ResourceLeaseManager.claim(task_id, session_id, resources, ttl_seconds) -> list[ResourceLease]`
- `release(lease_id, current_hash=None) -> ResourceLease`
- `list_active() -> list[ResourceLease]`

- [ ] **Step 1: Write failing overlap/atomicity tests**

Cover FILE=FILE, TREE descendant conflicts, exact LOGIC/CONTRACT/GLOBAL conflicts, non-overlapping resources, two-session denial, and a multi-resource claim where one conflict causes zero inserts.

- [ ] **Step 2: Verify RED**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_resource_leases.py -q`
Expected: missing `lease_rules` / `leases` implementation.

- [ ] **Step 3: Implement pure overlap rules and transactional claim**

Normalize path separators and case for Windows resource keys. `claim()` opens `BEGIN IMMEDIATE`, queries non-released WRITE leases, checks every requested WRITE resource, then inserts the full set only when no conflict exists.

- [ ] **Step 4: Verify concurrency behavior**

Add a multiprocessing test with two independent processes racing for the same resource. Exactly one claim succeeds and one receives a structured conflict result/exception.

- [ ] **Step 5: Run Task 1+2 tests**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_workspace_store.py tests/devcoord/test_resource_leases.py -q`
Expected: PASS.

### Task 3: Agent sessions, heartbeat, stale ownership, takeover

**Files:**
- Create: `uni/devcoord/sessions.py`
- Create: `uni/devcoord/takeover.py`
- Test: `tests/devcoord/test_agent_sessions.py`

**Interfaces:**
- `AgentSessionManager.register(...) -> AgentSession`
- `heartbeat(session_id, ttl_seconds) -> AgentSession`
- `mark_stale(now=None) -> list[AgentSession]`
- `ControlledTakeover.prepare(stale_session_id, snapshot) -> TakeoverRecord`

- [ ] **Step 1: Write failing lifecycle tests**

Test register -> ACTIVE, heartbeat refresh, expiration -> STALE, and that stale sessions with active WRITE leases keep those leases reserved.

- [ ] **Step 2: Verify RED**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_agent_sessions.py -q`
Expected: missing lifecycle modules.

- [ ] **Step 3: Implement session lifecycle and takeover record**

Persist heartbeats transactionally. Stale marking changes session/lease state to STALE but never deletes or releases leases. Takeover requires a non-empty preserved snapshot reference and emits an audit event.

- [ ] **Step 4: Verify GREEN**

Run Task 3 tests plus Tasks 1-2 tests; expected PASS.

### Task 4: Status and audit query surface

**Files:**
- Create: `uni/devcoord/workspace_status.py`
- Test: `tests/devcoord/test_workspace_status.py`

**Interfaces:**
- `WorkspaceStatus.summary() -> WorkspaceSummary`
- `WorkspaceStatus.resource(resource_type, resource_key) -> list[ResourceLease]`
- `WorkspaceStatus.events(limit=...) -> list[WorkspaceEvent]`

- [ ] **Step 1: Write failing status tests**

Assert objective counts for ACTIVE/STALE sessions and active/conflicting leases, plus lookup by normalized resource key.

- [ ] **Step 2: Verify RED, implement minimal query service, verify GREEN**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_workspace_status.py -q`
Expected final: PASS.

### Task 5: Phase 1 regression and handoff

**Files:**
- Modify only if needed: `uni/devcoord/__init__.py`
- Test: all `tests/devcoord/**`
- Read-only verification: protected invariant checker/tests.

- [ ] **Step 1: Export only stable public MAWC types if useful**

Do not alter existing `DevelopmentCoordinator` interfaces. Avoid broad imports that introduce side effects.

- [ ] **Step 2: Run MAWC and existing devcoord tests**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord -q`
Expected: all PASS.

- [ ] **Step 3: Run protected verification checks**

Run: `C:\LLM\python312\python.exe scripts\check_verification_invariant.py`
Run: `C:\LLM\python312\python.exe -m pytest tests/test_verification_invariant.py -q`
Expected: PASS without editing protected files.

- [ ] **Step 4: Review ownership and commit narrowly**

Run `git status --short`, inspect diffs only for MAWC files, stage explicit MAWC paths, verify `git diff --cached --name-only`, and never include unrelated dirty-tree changes.

- [ ] **Step 5: Report measured result**

Report exact changed files, test commands/counts, prevented conflict behaviors proven by tests, and Phase 2 remaining work. Do not claim runtime agent automation until runner/worktree integration is actually implemented and observed.
