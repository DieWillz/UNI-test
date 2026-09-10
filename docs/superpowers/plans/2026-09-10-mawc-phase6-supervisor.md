# MAWC Phase 6 Development Supervisor Plan

**Goal:** Give UNI a deterministic supervisor tick that keeps agent processes alive, assigns runnable work to free sessions, and produces objective development reports.

**Architecture:** `DevelopmentSupervisor` composes `TaskDispatcher`, `LocalAgentRunner`, and agent launch profiles. It does not edit code itself and does not mark tasks VERIFIED. `DevelopmentReporter` reads SQLite state only.

**Safety rules:**
- only registered ACTIVE, unbound sessions may receive work;
- agent commands are explicit argv builders and always run through LocalAgentRunner;
- a VERIFYING/STALE session never receives another task;
- process exit remains VERIFYING until a separate verification manager decides;
- report counts derive from persisted state, never estimated percentages;
- supervisor failures emit audit events and do not trigger destructive git cleanup.

## Task 1: Reporting and session listing

Add `WorkspaceStore.list_sessions()` and `DevelopmentReporter.snapshot()`. Report exact task/session/lease counts and critical event counts.

## Task 2: Supervisor tick

Add `AgentLaunchProfile` and `DevelopmentSupervisor.tick()`. First poll existing runs; then dispatch only free ACTIVE sessions with a configured profile. Keep active run ids in supervisor-owned state.

## Task 3: Tests and verification

Use a real temporary git repository and Python child process. Verify automatic dispatch, worktree cwd, exit-to-VERIFYING, no reassignment while VERIFYING, objective report counts, MAWC regression, invariant checks, and py_compile.
