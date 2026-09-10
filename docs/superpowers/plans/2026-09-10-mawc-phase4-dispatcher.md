# MAWC Phase 4 Dispatcher Implementation Plan

**Goal:** Safely bind a reserved MAWC task to an isolated task worktree and the owning `AgentSession`.

**Architecture:** `TaskDispatcher` composes `TaskScheduler`, `WorktreeManager`, `WorkspaceStore`, and `ResourceLeaseManager`. It does not launch external agents yet.

**Safety rules:**
- create worktree only after successful reservation;
- never copy shared dirty changes into task worktrees;
- if worktree creation fails, release only leases from that reservation;
- restore only that task from CLAIMED to READY and clear its assignment;
- do not mutate unrelated tasks, sessions, branches, or worktrees;
- no reset/clean/stash/checkout/merge/remove operations;
- every state transition emits an audit event.

### Task 1: Successful prepare

Create `uni/devcoord/dispatcher.py` and `tests/devcoord/test_dispatcher.py`.

`TaskDispatcher.prepare(session_id, base_ref="HEAD")` should reserve the next task, create its task-scoped worktree, bind task/worktree to the session, and return a `PreparedDispatch`.
### Task 2: No-reservation side-effect guard

If scheduler returns `None`, dispatcher returns `None` and must not create a worktree or mutate the session.

### Task 3: Worktree failure rollback

Force a branch/path collision after reservation. Assert:
- raised error is preserved;
- task returns to READY with no assigned session;
- reservation leases become RELEASED;
- session remains unbound;
- `dispatch.failed` is recorded.

### Task 4: Verification

Run dispatcher focused tests, the MAWC test set, protected invariant checks, and py_compile for MAWC-owned modules. Review staged paths before committing.

External Hermes/Codex process launch is explicitly Phase 5; this phase only prepares a safe execution workspace.