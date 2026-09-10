# MAWC Phase 2 Worktree Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add task-scoped git worktrees for new UNI development tasks without moving or overwriting the current dirty shared working tree.

**Architecture:** `WorktreeManager` is an additive devcoord service. It creates one branch/worktree per task from a committed base ref and never imports uncommitted shared-tree changes. Checkpoints are metadata-only in this phase; destructive cleanup is out of scope.

**Tech Stack:** Python 3.12, stdlib `subprocess`, `pathlib`, pytest, git.

**Spec:** `docs/superpowers/specs/2026-09-10-mawc-design.md`

## Global Constraints

- Unknown dirty-tree changes belong to another agent.
- Never use `git reset --hard`, `git clean`, mass checkout, or whole-tree restore.
- Existing shared-tree dirty changes must not be moved into new worktrees.
- New worktrees are task-scoped, not agent-scoped.
- Protected verification and merge gates remain unchanged.
- Every production behavior is introduced test-first.

---

### Task 1: Task-scoped worktree creation

**Files:**
- Create: `uni/devcoord/worktrees.py`
- Create: `tests/devcoord/test_worktrees.py`

**Interfaces:**
- `WorktreeManager.create(agent_id, task_id, base_ref="HEAD") -> WorktreeRef`
- `WorktreeRef.path`, `.branch`, `.task_id`, `.agent_id`
- [ ] **Step 1: Write failing creation/isolation tests**

Create a temporary git repository, commit a baseline file, then make an uncommitted shared-tree edit. Assert the new task worktree contains the committed baseline rather than the dirty edit.

- [ ] **Step 2: Verify RED**

Run: `C:\LLM\python312\python.exe -m pytest tests/devcoord/test_worktrees.py -q`
Expected: FAIL because `uni.devcoord.worktrees` does not exist.

- [ ] **Step 3: Implement minimal creation service**

Use `git worktree add -b <task-branch> <path> <base-ref>`. Validate ids into safe path segments, resolve all paths under the configured root, and refuse collisions rather than reusing an ambiguous existing directory.

- [ ] **Step 4: Verify GREEN and regression**

Run the focused test, then `tests/devcoord/test_workspace_store.py`, `test_resource_leases.py`, `test_agent_sessions.py`, and `test_workspace_status.py`.

### Task 2: Worktree checkpoint metadata

**Files:**
- Modify: `uni/devcoord/worktrees.py`
- Modify: `tests/devcoord/test_worktrees.py`

**Interfaces:**
- `WorktreeManager.snapshot(ref) -> WorktreeSnapshot`

- [ ] **Step 1: Add failing snapshot test**

Assert snapshot captures branch, HEAD commit, porcelain status and diff text without modifying either worktree or canonical repository.

- [ ] **Step 2: Implement read-only snapshot and verify GREEN**

Use only read-only git commands (`rev-parse`, `status --porcelain`, `diff --binary`). Do not stash, reset, checkout, clean, commit, merge, or remove worktrees.

### Task 3: Phase 2 verification

- [ ] Run all `tests/devcoord` tests.
- [ ] Run protected verification invariant script and tests.
- [ ] Compile only MAWC-owned modules; report unrelated foreign-file syntax failures separately.
- [ ] Commit only Phase 2 files after staged-file review.
