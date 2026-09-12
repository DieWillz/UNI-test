# UNI Balanced Visible + Verified Skill Memory Design

## Goal

Make UNI think structurally and fast, act visibly when user-facing interaction matters, verify every side effect independently, and reuse only previously verified workflows.

Core rule:

`Understand structurally -> Act visibly -> Verify independently -> Remember only verified success -> Reuse semantically, never blindly by coordinates.`

## User experience

`BALANCED_VISIBLE` is the default execution mode. UNI may use DOM, UIA, OCR, VLM, filesystem reads, and other deterministic observations silently to understand the scene. When a normal user-facing interaction is understandable as a mouse/keyboard action, UNI should visibly move the cursor, focus the target, click, type, select, or drag so the user can follow what is happening.

Visible execution must be quick rather than theatrical. Typical cursor movement should remain roughly 150-500 ms depending on distance. The action badge may mark the target/action, but computation and verification remain invisible unless surfaced as status text.

## Execution modes

Three modes are supported:

- `VISIBLE`: prefer physical mouse/keyboard for user-facing interaction whenever safely possible.
- `BALANCED_VISIBLE`: default; visible physical interaction for normal controls, direct methods for observation, computation, filesystem/API work, and cases where visible emulation would reduce reliability.
- `FAST`: prefer DOM/UIA/direct APIs; physical interaction is fallback when structural execution is unavailable or inappropriate.

## Structural understanding vs visible execution

Perception and execution are separate concerns.

UNI should use the most reliable perception source in this order where applicable:

1. browser DOM for browser controls;
2. Windows UIA for desktop controls;
3. OCR for readable visual text not exposed structurally;
4. VLM/vision for visual-only surfaces;
5. raw coordinates only as a last-mile physical actuator, never as durable semantic identity.

A user-visible action may still be driven by structural understanding. Example: UIA identifies the exact `Save` button and its current rectangle, then the visible executor moves the cursor to that rectangle and clicks it. Afterward UIA or another independent source verifies the postcondition.

## Deterministic execution policy

Execution method selection is runtime policy, not free-form LLM reasoning.

Create an `ExecutionPolicy` that receives execution mode, action metadata, target/scene facts and available capabilities, and returns an `ExecutionDecision`.

The decision must record:

- chosen execution method;
- whether physical input is required;
- reason for the choice;
- whether a trustworthy screen-space target is required;
- whether direct structural fallback is permitted.

## Visible Windows actions

Visible Windows execution should be implemented in a focused component, not by duplicating `ComputerCapability`.

It consumes a freshly resolved `UIElement` and existing low-level primitives. Typical behavior:

- button/menu/list item: move humanly to fresh bbox, optionally show badge, click;
- textbox/document: move/focus visibly, then type or paste, followed by fresh value/text readback;
- checkbox/radio: visible click when safe, then fresh checked-state verification;
- combobox/selectable list: visible selection when stable, otherwise direct UIA selection in `BALANCED_VISIBLE`;
- drag/drop or visual canvas: physical mouse path is normal execution.

`InputBroker` remains the single physical-input owner. STOP must invalidate the active lease and interrupt visible execution promptly.

## Browser visible actions

DOM remains the preferred browser targeting source. Physical execution is permitted only when the runtime can reliably map the DOM element rectangle to current screen coordinates, accounting for the active tab/window, viewport, zoom/DPI and browser chrome offsets.

If mapping is stale, ambiguous or untrusted, `BALANCED_VISIBLE` falls back to the structural DOM action instead of guessing a coordinate.

## Verification

Visible behavior never changes the verification contract. Side effects still require a fresh observation after the action and an explicit postcondition. UI animation, cursor motion, action badges and tool acknowledgements are not verification evidence.

## Operator progress events

Core execution may emit typed, optional progress events such as `locating`, `moving`, `focusing`, `acting`, `observing`, `verifying`, `verified` and `not_verified`.

The event stream exists for transparency and UI presentation only. WebUI, Telegram and desktop clients may subscribe later, but they do not decide whether a task succeeded.

## Verified Skill Memory

Durable skill memory stores reusable semantic workflows, not screenshots or blind coordinate macros.

Each skill should carry:

- normalized intent/goal;
- application/window context constraints;
- semantic action sequence;
- semantic target identity per step;
- explicit postconditions;
- required permission level;
- verified success/failure statistics;
- consecutive verification failures;
- timestamps and schema version.

Bounding boxes or coordinates may be cached as acceleration hints but must be discarded/re-resolved whenever the context changes.

Sensitive values must not be learned. Password fields, secrets, auth tokens, clipboard secrets and other sensitive text are excluded from durable skill payloads.

## Skill persistence and reuse

Use stdlib SQLite at `runtime/operator/skills.sqlite3`. The store is runtime state, not source code, and must support schema versioning and bounded queries.

Only `TaskOutcome.status == VERIFIED` may create or strengthen a skill. `FAILED`, `BLOCKED`, `INTERRUPTED`, `NOT_VERIFIED`, or a successful low-level tool call never teaches durable behavior.

Reuse flow:

`goal -> normalized candidate lookup -> fresh scene -> context match -> semantic target re-resolution -> normal MissionPlan -> normal permissions -> normal executor -> fresh verification`.

A learned skill never bypasses `MissionExecutor`, `PermissionGate`, `InputBroker`, STOP, or `PostconditionVerifier`.

Start with deterministic normalized matching. Do not add embeddings/vector search until real usage demonstrates a need.

Confidence may use `(successes + 1) / (successes + failures + 2)` as a bounded initial estimate. It is only a ranking/reuse signal; fresh context validation and fresh verification remain mandatory.

Automatic reuse is disabled after 2 consecutive verification failures. A later normal-planner VERIFIED execution may relearn/update the recipe.

## Relationship to legacy trajectories

`uni/tools/trajectory_store.py` remains legacy/reference logging. It is not the authoritative new skill store and must not regain hidden global writes from tests or standalone visual agents.

## Error handling

Missing or ambiguous semantic target: do not act; reobserve/replan using existing bounded recovery.
Stale bbox/DOM geometry: reobserve; never replay old coordinates blindly.
Verification failure: do not promote to success; update failure statistics only when an attempted learned skill can be identified safely.
Store unavailable/corrupt: continue without learning/reuse rather than blocking basic Operator execution.

## Testing and acceptance

Unit tests cover execution-policy decisions, safe/unsafe physical targeting, STOP behavior, event emission, skill persistence rules, context matching, sensitive-data exclusion and confidence disable/re-enable logic.

Live Windows acceptance uses isolated test windows, not the user's working applications. It must exercise visible cursor movement plus fresh UIA verification.

Browser acceptance uses deterministic local pages and verifies that structural targeting remains authoritative even when physical execution is chosen.

A full acceptance scenario must prove that the first unknown workflow is planned normally, becomes durable only after VERIFIED completion, survives process restart, and the second matching run uses the skill fast path while still revalidating context and reverifying every side effect.

Changed UI must invalidate the fast path and safely return to ordinary perception/planning.

## Non-goals for the first implementation

- no embedding/vector skill retrieval;
- no cloud skill service;
- no free-form model-written executable scripts as skills;
- no blind screenshot/coordinate macros;
- no automatic permissions elevation from learned history;
- no WebUI-specific execution logic in the Operator core;
- no second Brain, Agent, Operator or ComputerCapability.

## Shared coordination

Cross-agent orientation and current ownership are documented in:
`docs/handoffs/UNI_OPERATOR_SHARED_ROADMAP.md`.

The detailed implementation sequence is documented in:
`docs/superpowers/plans/2026-09-11-uni-balanced-visible-skill-memory.md`.
