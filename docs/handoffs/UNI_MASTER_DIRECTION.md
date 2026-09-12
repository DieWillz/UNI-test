# UNI Master Direction

> OWNER-DIRECTED, READ-MOSTLY. This is the project-wide source of truth for architectural decisions made by the repository owner.
> Every development agent MUST read this file before starting or accepting new work.

## Core product direction

UNI is one universal agent and one shared core. Do not create competing brains, planners, memories, operators, or transport-specific agents.

Permanent operating principle:

`Understand structurally -> Acknowledge quickly -> Make a mini-plan -> Act visibly when useful -> Verify independently -> Report -> Remember only verified success.`

Permanent verification invariant:

`COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`

A low-level tool success is never task success. Missing, stale, ambiguous, or failed evidence means `not_verified`.

## User-visible command lifecycle

Every user message is internally classified and decomposed. Operational commands must not disappear into a long silent reasoning period.

For non-trivial operational work UNI should: acknowledge quickly, expose a short mini-plan, emit real progress events while executing, independently verify side effects, and give a final factual report.

Progress must come from runtime state, not invented narration. Replanning is allowed and must be surfaced as a plan update rather than hidden.

## Visible interaction policy

Default Operator mode is `BALANCED_VISIBLE`.

DOM/UIA/OCR/VLM and deterministic APIs may be used silently for understanding, targeting, calculation, and verification. Normal user-facing controls should be acted on visibly when that remains reliable: visible cursor movement, focus, click, typing, selection, and drag/drop.

Direct filesystem/API/DOM/UIA operations remain appropriate when visible emulation would be pointless, slower, or less reliable.

The LLM does not decide ad hoc whether an action is visible. A deterministic execution policy chooses the method.

## Verified skill memory

Repeated successful workflows may become reusable skills only after independent verification.

Skills store semantic identity and context: application/window identity, role, accessible name/text, automation id or DOM identity, expected postconditions, and success/failure history.

Raw coordinates are never authoritative memory. They may only be transient hints. If semantic context changed or a target cannot be freshly resolved, the skill must fall back to normal perception/planning and may be relearned after a newly verified success.

## Transitional autonomous seam (owner directive)

`uni/autonomous.py`, `uni/autonomous_session.py`, `uni/control_queue.py`, `uni/xtoys_control_coordinator.py`, and current integration touches in `uni/agent.py` are temporary transitional paths outside the canonical `uni/operator/**` pipeline.

They MUST NOT evolve into a competing second Operator. Until an explicit consolidation owner is assigned, agents MUST treat the current dirty versions of these paths as owner-reserved and MUST NOT add features, refactor, overwrite, or absorb them.

Before UNI is considered production-ready, their behavior MUST be reconciled into the single Operator pipeline. After independently verified parity, each legacy path must either become a thin compatibility adapter or be retired. No consolidation may weaken `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`.

## Multi-agent development rule

The repository is a shared workspace. Unknown uncommitted changes belong to another agent.

Before any development work every agent MUST read:
1. `AGENTS.md`
2. this file
3. `docs/handoffs/UNI_ACTIVE_WORK.md`
4. the roadmap/spec/handoff for its assigned subsystem
5. current `git status` and target-file diff

No agent may overwrite another active lane just to make its own task easier. Cross-lane work must use an interface, a handoff request, or an explicitly transferred lease/ownership.

Shared-workspace commits MUST be lane-isolated. No agent may create a bulk commit that stages or commits unrelated dirty changes from other lanes. Each ACTIVE lane must stage only its own owned paths and commit its work separately after its targeted verification is green; foreign dirty files must remain untouched.

Any new owner-approved architectural requirement from chat must be added to this master direction (or a linked subsystem spec) before production implementation so later agents do not depend on conversation history.

## Synchronization contract

The project has one content-derived `direction_revision`. It is SHA-256 over the full contents of `UNI_MASTER_DIRECTION.md` plus a canonical representation of the machine-readable assignment block in `UNI_ACTIVE_WORK.md`.

Only assignment semantics participate from `UNI_ACTIVE_WORK.md`: `agent`, `task`, `status`, `exclusive_paths`, `read_only_paths`, `dependencies`, and `updated_at`. Narrative notes, history outside the machine block, TOML comments, formatting, assignment order, and path-list order MUST NOT make agents stale.

Changes to owner directives in this file, lane ownership, assigned task, status, dependencies, protected/read-only scope, exclusive scope, or `updated_at` MUST change the revision.

Every agent MUST explicitly acknowledge the current revision after reading the required direction documents. A stale or missing acknowledgement is fail-closed and MUST block new development writes until the agent deliberately resynchronizes. The gate MUST NOT automatically accept a newer revision on behalf of an agent.

The executable primitive is `uni.direction_sync`. It is project-wide and independent of MAWC state; the existing MAWC/DevCoord coordinator consumes this primitive later rather than creating a second coordinator or lease system.

## Canonical subsystem roadmaps

- Operator: `docs/handoffs/UNI_OPERATOR_SHARED_ROADMAP.md`
- Balanced Visible + Skill Memory spec: `docs/superpowers/specs/2026-09-11-uni-balanced-visible-skill-memory-design.md`
- Telegram: `docs/superpowers/specs/2026-09-10-uni-telegram-continuous-design.md`
- MAWC/DevCoord: `docs/superpowers/specs/2026-09-10-mawc-design.md` and its phase plans
- Product Integration: `docs/superpowers/specs/2026-09-12-uni-product-integration-design.md`

## Change policy

This file is read-mostly. Agents may update it only to record an owner-approved decision, resolve a factual contradiction, or maintain links/revisions required by the synchronization system.

Do not silently weaken or delete owner directives. If two directives conflict, stop the conflicting implementation and surface the conflict for owner resolution.
