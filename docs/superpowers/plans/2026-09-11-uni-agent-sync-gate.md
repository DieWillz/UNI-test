# UNI Agent Synchronization Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require every development agent to synchronize with owner direction and live assignments before starting new work.

**Architecture:** Owner direction and active work remain markdown source-of-truth files. A leaf MAWC utility hashes them, persists per-agent acknowledgement state atomically, and fails closed on stale/missing state. Existing MAWC scheduler/leases consume this gate later; no second coordinator or lease system is created.

**Tech Stack:** Python 3.12 stdlib (`hashlib`, `json`, `pathlib`, `tempfile`, `argparse`), pytest, existing MAWC/DevCoord.

**Spec:** `docs/superpowers/specs/2026-09-11-uni-agent-sync-gate-design.md`

## Global Constraints

- Never reset/clean/restore unknown changes in the shared workspace.
- `UNI_MASTER_DIRECTION.md` is owner-directed/read-mostly.
- `UNI_ACTIVE_WORK.md` is the live assignment registry.
- Missing or stale acknowledgement fails closed for NEW work.
- Do not edit currently dirty dispatcher/scheduler/lease files owned by another DevCoord agent.
- Do not weaken `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`.

---

### Task 1: Shared source-of-truth files

**Files:** `AGENTS.md`, `docs/handoffs/UNI_MASTER_DIRECTION.md`, `docs/handoffs/UNI_ACTIVE_WORK.md`

- [x] Record owner-approved architecture and command lifecycle direction.
- [x] Record current parallel lane ownership for GPT UNI Night, Hermes, DevCoord/MAWC, and inactive browser handoff.
- [x] Make reading both files mandatory in `AGENTS.md` before development.

### Task 2: Revision and acknowledgement gate

**Files:**
- Create: `uni/devcoord/direction_sync.py`
- Create: `tests/devcoord/test_direction_sync.py`

**Interfaces:**
- `DirectionSnapshot.load(repo_root: Path) -> DirectionSnapshot`
- `DirectionSyncGate.ack(agent_id: str) -> AgentDirectionAck`
- `DirectionSyncGate.check(agent_id: str) -> SyncCheck`
- `DirectionSyncGate.show() -> str`

- [ ] Write RED tests for missing ack, valid ack, stale master, stale active work, wrong agent, corrupted ack, and restart persistence.
- [ ] Run only `tests/devcoord/test_direction_sync.py` and confirm expected RED failures.
- [ ] Implement content-derived SHA-256 revisions and atomic JSON acknowledgement persistence under `.uni-dev/coordination/agent-sync/`.
- [ ] Make agent-id filenames safe and fail closed on missing source files or invalid JSON.
- [ ] Re-run the targeted tests until GREEN.

### Task 3: CLI preflight contract

**Files:**
- Modify: `uni/devcoord/direction_sync.py`
- Modify: `AGENTS.md`
- Test: `tests/devcoord/test_direction_sync.py`

- [ ] Add RED subprocess tests for `show`, `ack --agent`, and `check --agent` exit codes.
- [ ] Implement `python -m uni.devcoord.direction_sync show|ack|check --agent <id>`.
- [ ] Update `AGENTS.md` with the exact preflight commands.
- [ ] Verify a stale revision exits nonzero and an acknowledged current revision exits zero.

### Task 4: MAWC integration handoff

**Files:**
- Modify only after ownership release: current MAWC assignment/start path under `uni/devcoord/**`
- Update: `docs/handoffs/UNI_ACTIVE_WORK.md`

**Interfaces:**
- consume `DirectionSyncGate.check(agent_id)` before assigning a new task or new exclusive write resource
- existing MAWC lease/resource ownership remains authoritative

- [ ] Identify the exact current assignment/start integration point from the DevCoord lane handoff.
- [ ] Add a RED integration test showing a stale agent cannot start a newly assigned task.
- [ ] Integrate the leaf gate without duplicating leases/scheduler state.
- [ ] Add GREEN coverage for current ack and stale ack.
- [ ] Record ownership transfer/handoff in `UNI_ACTIVE_WORK.md`.

If dirty target files are still owned by another active agent, do not modify them; leave this task explicitly BLOCKED_BY_LANE and continue Task 5.

### Task 5: Verification and project handoff

**Files:**
- Update: `docs/handoffs/UNI_ACTIVE_WORK.md`
- Update: `docs/handoffs/UNI_MASTER_DIRECTION.md` only for factual links/commands established by implementation

- [ ] Run `tests/devcoord/test_direction_sync.py`.
- [ ] Run the non-conflicting DevCoord targeted tests relevant to the integrated gate, if Task 4 is available.
- [ ] Run `C:\LLM\python312\python.exe scripts\check_verification_invariant.py`.
- [ ] Run `C:\LLM\python312\python.exe -m uni.check_architecture --strict`.
- [ ] Run `git diff --check` for files changed by this plan.
- [ ] Update active work status with exact tested results and any blocked integration.
