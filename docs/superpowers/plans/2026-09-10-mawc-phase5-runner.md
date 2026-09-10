# MAWC Phase 5 Local Agent Runner Plan

**Goal:** Run an external development agent only inside a prepared task worktree, keep runner-owned heartbeats, persist PID/log paths, and move completed execution into VERIFYING without releasing leases.

**Architecture:** `LocalAgentRunner` consumes `PreparedDispatch`. It launches an explicit argv list with `shell=False`, cwd fixed to the task worktree, and stdout/stderr redirected to task-scoped logs. The runner owns process observation; the LLM prompt does not own heartbeat.

**Safety rules:**
- never launch before dispatcher preparation;
- never use shell command strings;
- never run in the shared canonical working tree;
- process exit is not VERIFIED evidence;
- on exit move task/session/leases to VERIFYING;
- leases remain blocking through verification;
- no automatic merge, reset, clean, stash, checkout, or worktree removal;
- logs and snapshots are evidence, not completion claims.

## Task 1: Start and heartbeat

Create `uni/devcoord/runner.py` and `tests/devcoord/test_runner.py`.

`LocalAgentRunner.start(prepared, argv)` must reject empty argv, launch with cwd=`prepared.worktree.path`, persist PID on the existing session, and create task-scoped stdout/stderr logs. `tick(run_id)` must refresh the session and lease TTL while the process is alive.

## Task 2: Exit transition

When the child exits, capture a read-only worktree snapshot and persist exit code. Transition the owning `WorkspaceTask`, `AgentSession`, and every non-released lease for that session to VERIFYING. Do not mark VERIFIED or release resources even for exit code 0.

## Task 3: Verification

Run focused runner tests, all MAWC-owned tests, the protected verification invariant script/tests, and py_compile for MAWC-owned modules. Commit only Phase 5 files after staged review.
