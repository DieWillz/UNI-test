# UNI Multi-Agent Workspace Coordinator Design

## Goal

Build a development supervisor for `C:\LLM\UNI` that safely coordinates multiple AI agents working at the same time without overwriting each other, while preserving UNI's protected verification invariant.

## Core decision

UNI is the single authority for task assignment and resource ownership. Agents do not write coordination state directly; they request work and leases through the coordinator runtime.

The first release adds a new MAWC runtime beside the existing `DevelopmentCoordinator`. Existing `CoordinationStore` JSON state and provider orchestration remain intact until migration is proven safe.

## Non-negotiable invariants

- Never weaken `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`.
- Never treat process exit, HTTP 200, a green unit test, or model narration as user-visible completion evidence by itself.
- Unknown dirty-tree changes belong to another agent.
- No destructive whole-tree git operations.
- Protected files keep the existing owner-review gate.
- A resource remains WRITE-locked while its task is VERIFYING.
- Stale ownership is never silently discarded when dirty changes may exist.

## Architecture

`DevelopmentSupervisor` sits above existing devcoord components and composes: `WorkspaceStore`, `AgentSessionManager`, `ResourceLeaseManager`, `TaskScheduler`, `WorktreeManager`, `WorkspaceMonitor`, `VerificationManager`, `MergeQueue`, and `DevelopmentReporter`.

MAWC state lives in `.uni-dev/coordination/workspace.sqlite`. SQLite uses WAL mode, foreign keys, busy timeout, and explicit write transactions for claim/release operations.

## Resource model

Resource types are `FILE`, `TREE`, `LOGIC`, `CONTRACT`, and `GLOBAL`. Access modes are `READ` and `WRITE`.

WRITE is exclusive against overlapping WRITE claims. TREE conflicts with descendant FILE/TREE resources. LOGIC/CONTRACT/GLOBAL conflict by exact normalized key. READ leases are informational in v1 and do not block WRITE unless a future protected contract policy explicitly opts in.

Each lease records: `lease_id`, `task_id`, `agent_session_id`, `resource_type`, `resource_key`, `access_mode`, `state`, `base_hash`, `current_hash`, `created_at`, `heartbeat_at`, `expires_at`, and `released_at`.

Lease states are `CLAIMED`, `ACTIVE`, `VERIFYING`, `BLOCKED`, `CONFLICT`, `STALE`, `HANDOFF`, and `RELEASED`.

## Agent sessions

An `AgentSession` identifies an executor instance, not merely a provider name. It records agent id/display name, task id, process identity when known, worktree path, capabilities, state, heartbeat, start time, and last observation.

Heartbeat is owned by the runner/supervisor process, not by LLM prompt compliance. Missing heartbeat plus dead runner marks a session STALE.

STALE does not automatically release dirty WRITE resources. The supervisor first snapshots status/diff metadata and creates a controlled takeover record.

## Task/worktree model

New implementation tasks should run in task-scoped worktrees such as `.uni-dev/worktrees/hermes/UNI-142/`, with one branch per task. Existing dirty shared-tree work is transitioned gradually and is not redistributed automatically.

## Claim flow

An agent or scheduler requests the smallest required resource set. `ResourceLeaseManager.claim()` normalizes resources, opens an immediate SQLite transaction, checks active overlapping leases, and either inserts all requested leases atomically or inserts none.

Dynamic scope expansion uses the same claim path. If a requested resource is busy, the task records a resource request and the scheduler may assign independent work instead of blocking the whole agent.

## Ownership auditing

At claim time, FILE resources capture a baseline SHA-256 when the file exists. During work, `WorkspaceMonitor` compares changed paths against active WRITE leases.

A changed path with no matching WRITE lease is emitted as `UNOWNED_CHANGE`. A changed path owned by a different active session is `OWNERSHIP_VIOLATION`. Neither event is silently accepted into a verified task.

## Controlled takeover

Takeover requires: stale/dead previous session, preserved diff/status snapshot, explicit takeover event, and a new lease owner. In shared-tree mode, takeover must not overwrite dirty content. In task worktrees, takeover may reuse or clone the preserved task worktree after inspection.

## Scheduling

Tasks carry priority, dependencies, required capabilities, requested resources, and verification commands. The scheduler only dispatches READY tasks whose dependencies are satisfied and whose initial resource set can be claimed.

If the preferred task conflicts, the scheduler chooses the next compatible READY task. If no task is runnable, the supervisor reports `NO_RUNNABLE_TASKS` instead of fabricating progress.

## Verification and merge

A task transitions `PLANNED -> CLAIMED -> ACTIVE -> VERIFYING -> VERIFIED -> READY_TO_MERGE`. Failure branches include `BLOCKED`, `CONFLICT`, `FAILED`, `STALE`, and `ABANDONED`.

`VERIFIED` requires fresh evidence recorded through the existing protected verification policy. Leases stay active through VERIFYING and release only after the verification record is persisted.

V1 does not automatically merge protected/core changes. Safe changes may enter a merge queue, but existing human confirmation semantics remain authoritative until a separate approved merge-policy change.

## Reporting

`DevelopmentReporter` produces objective counts only: active sessions, READY/RUNNING/VERIFIED/BLOCKED tasks, active/stale leases, prevented conflicts, unowned changes, test results, and merge-queue entries.

Periodic reports must not invent percentage completion. Progress is expressed as verified task counts and explicit blockers. Critical events are reported immediately: ownership violations, protected-file changes, repeated verification failure, failed recovery, unresolved merge conflict, or no runnable tasks.

## CLI/runtime surface

Initial commands: `status`, `status <resource>`, `claim`, `release`, `heartbeat`, `conflicts`, `sessions`, and `takeover`. The library API remains primary; CLI is a thin adapter suitable for Hermes/Codex wrappers.

## Rollout

Phase 1: SQLite store, sessions, leases, conflict detection, audit events, controlled stale handling.

Phase 2: task-scoped worktrees and runner-owned heartbeat/checkpoints.

Phase 3: dependency-aware scheduler and automatic reassignment on conflict.

Phase 4: `DevelopmentSupervisor`, WebUI/Telegram reporting, and operator commands through normal UNI conversation.

## Acceptance criteria for Phase 1

Two independent processes cannot both acquire conflicting WRITE leases; failed multi-resource claims are atomic; TREE overlap works; heartbeat refreshes TTL; stale dirty ownership is not auto-released; release records final hash; status/audit history is queryable; existing devcoord tests and verification invariant remain green.
