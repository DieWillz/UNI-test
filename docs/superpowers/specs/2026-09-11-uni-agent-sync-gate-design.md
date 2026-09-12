# UNI Agent Synchronization Gate Design

## Goal

Make project-wide architectural direction and active lane ownership mandatory shared context for every development agent before it starts new work.

## Source of truth

`docs/handoffs/UNI_MASTER_DIRECTION.md` contains owner-approved product and architecture directives. It is read-mostly and changes only when the owner approves a new direction or a factual contradiction/link must be repaired.

`docs/handoffs/UNI_ACTIVE_WORK.md` contains live assignments, lane ownership, conflicts, dependencies, and acceptance criteria. Each active agent updates only its own assignment block unless ownership is transferred.

`AGENTS.md` is the mandatory repository entry point and requires both documents to be read before development.

## Revision model

Revisions are content-derived SHA-256 hashes; no human-maintained revision number is authoritative.

`direction_revision = sha256(UNI_MASTER_DIRECTION.md bytes)`

`work_revision = sha256(UNI_ACTIVE_WORK.md bytes)`

An acknowledgement records both revisions plus agent id and acknowledgement time. The current task may continue safely after unrelated work-registry changes, but a stale acknowledgement blocks accepting/starting the next task or claiming a new resource.

## Executable preflight

A small sync service/CLI exposes three operations:

- `show`: print the current master direction and active-work registry with their revisions.
- `ack`: persist that an agent synchronized to the exact current revisions.
- `check`: fail closed when acknowledgement is missing, unreadable, belongs to another agent, or is stale.

Acknowledgements live under `.uni-dev/coordination/agent-sync/` and are runtime state, not source-controlled product data.

The gate must use atomic writes and safe agent-id filenames. It must not execute arbitrary content from markdown files.

## MAWC integration

The sync contract is a leaf utility owned by DevCoord/MAWC. Scheduler/dispatcher integration must call `check` before a new assignment starts or a new exclusive resource is claimed.

Existing MAWC resource leases remain the authority for ownership; this feature must not create a second lease system.

Because the current DevCoord lane is actively modified by another agent, this phase may add the independent sync module and tests without editing dirty dispatcher/scheduler files. Integration becomes a handoff requirement for the DevCoord lane owner.

## Failure behavior

Missing source files, malformed acknowledgement state, hash mismatch, or filesystem errors fail closed. The result must explain which revision is stale without exposing secrets.

A stale agent may inspect/read files and finish a currently-running safe operation, but may not accept a new task or acquire newly assigned write ownership until it acknowledges current context.

## Acceptance

The gate must prove: first-time agent is blocked; acknowledged agent passes; modifying master direction makes it stale; modifying active work makes it stale; another agent cannot reuse the acknowledgement; corrupted state fails closed; atomic acknowledgement survives restart.
