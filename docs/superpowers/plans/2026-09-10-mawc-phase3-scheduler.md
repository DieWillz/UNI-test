# MAWC Phase 3 Scheduler Implementation Plan

**Goal:** Persist a development backlog and let UNI choose/reserve the next runnable task for an agent without waiting on resource conflicts.

**Architecture:** Add `WorkspaceTask` persistence to `WorkspaceStore` and a `TaskScheduler` service beside existing devcoord orchestration. Scheduler decisions are deterministic and auditable; resource claims remain delegated to `ResourceLeaseManager`.

**Constraints:**
- Do not modify legacy `DevelopmentCoordinator` behavior.
- Unknown dirty changes belong to other agents.
- No destructive git operations.
- Dependencies must be VERIFIED before dispatch.
- A conflicting preferred task is skipped; another runnable task may be selected.
- Never mark a task VERIFIED from model narration or process exit alone.
- TDD for every production behavior.

### Task 1: Persistent MAWC backlog

**Files:** `uni/devcoord/workspace_models.py`, `uni/devcoord/workspace_store.py`, `tests/devcoord/test_scheduler.py`.

Add `WorkTaskState` and `WorkspaceTask` with: id, title, priority, dependencies, required_capabilities, requested_resources, state, assigned_session_id, created_at, updated_at.
Acceptance:
- tasks round-trip through SQLite;
- dependency ids and requested resources survive serialization;
- list order is stable and priority-aware at scheduler level.

### Task 2: Runnable-task selection

**Files:** create `uni/devcoord/scheduler.py`, extend `tests/devcoord/test_scheduler.py`.

`TaskScheduler.ready_tasks(session_id)` must:
- load the target `AgentSession`;
- exclude non-PLANNED/READY tasks;
- require every dependency to be VERIFIED;
- require all task capabilities to be present in the session;
- order by priority descending, then creation/id deterministically.

Verify RED before production code, then GREEN.

### Task 3: Atomic reservation with conflict skip

`TaskScheduler.reserve_next(session_id, ttl_seconds=...)` must inspect READY candidates in order and ask `ResourceLeaseManager.claim()` for each task's complete resource set.
If a candidate conflicts, record/retain the conflict evidence and continue to the next compatible task instead of blocking the agent.

On successful reservation:
- all requested resources are claimed atomically;
- task state becomes CLAIMED;
- `assigned_session_id` is persisted;
- emit `task.claimed` audit event.

If no candidate can be reserved, return `None` without fabricating progress.

### Task 4: Task worktree assignment boundary

Add a small `DispatchAssignment` result containing task + leases. Worktree creation remains explicit and happens only after a successful reservation; never create a worktree for a task whose resources could not be claimed.

Phase 4 runner will bind the reservation to process launch and heartbeat. Do not start external agent processes in this phase.

### Task 5: Verification

Run:
- `C:\LLM\python312\python.exe -m pytest tests/devcoord -q`
- `C:\LLM\python312\python.exe scripts/check_verification_invariant.py`
- `C:\LLM\python312\python.exe -m pytest tests/test_verification_invariant.py -q`
- `py_compile` for MAWC-owned modules.

Review staged file names before each commit. Report foreign `uni/devcoord/sessions.py` separately and never overwrite it.