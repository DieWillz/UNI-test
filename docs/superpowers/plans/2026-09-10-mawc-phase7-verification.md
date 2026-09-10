# MAWC Phase 7 Verification Lifecycle

**Goal:** verify task worktrees with explicit argv commands and never confuse verified branch state with canonical integration.

**Model changes:**
- add `WorkspaceTask.verification_argv`;
- add `WorkTaskState.MERGED` for later integration;
- dependency scheduling will move to MERGED in Phase 8.

**Verification rules:**
- only `VERIFYING` tasks can be verified;
- commands run with `shell=False` in the task worktree;
- no configured verification means no automatic success;
- every command records argv, return code, stdout and stderr excerpts;
- all commands must pass before task becomes `VERIFIED`;
- process exit code from the agent itself is never verification.

**Lease/session policy:**
- verification does not release leases;
- session remains `VERIFYING` after successful verification;
- Phase 8 merge/integration decides when to release ownership and free the session;
- failed verification marks the task `FAILED` but preserves worktree evidence for inspection.

**Tests:**
1. successful explicit verification -> `VERIFIED`;
2. failing command -> `FAILED` with evidence;
3. empty verification config -> fail closed, never VERIFIED;
4. command cwd is the task worktree;
5. leases remain held until integration;
6. regression + protected invariant + py_compile.
