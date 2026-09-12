# UNI Operator Shared Roadmap

> **READ THIS FIRST for all agents working on UNI Operator / computer control / browser control / action memory.**
>
> This file is the shared direction-of-travel document. It is intentionally broader than a single agent handoff.
> `AGENTS.md` and `VERIFICATION_POLICY.md` remain authoritative if anything here conflicts with them.

Last coordinated update: 2026-09-11
Current integration owner for this lane: **GPT UNI Night**
Canonical repository: `C:\LLM\UNI`
Canonical package: `C:\LLM\UNI\uni`

## 1. Product direction

UNI should become a universal local operator that can understand Windows and browser interfaces, perform actions visibly enough for the user to follow, verify results independently, and learn from workflows that have actually succeeded.

The guiding rule is:

`Understand structurally -> Act visibly -> Verify independently -> Remember only verified success -> Reuse semantically, never blindly by coordinates.`

The user specifically prefers to **see UNI move the mouse, click, focus fields and type** for normal user-facing interactions. Structural methods such as DOM/UIA are still preferred for understanding targets and verifying results.

## 2. Default interaction philosophy

The default mode is `BALANCED_VISIBLE`.

In `BALANCED_VISIBLE`:

- DOM/UIA/OCR/VLM may work silently as UNI's perception and reasoning layer.
- Normal user-facing clicks should normally be performed with visible cursor movement when a safe physical target can be derived.
- Text entry should visibly focus the field; short text may be typed, while long text may use paste after visible focus to avoid artificial slowness.
- Checkbox, menu, button, list selection and drag/drop should be visible where reliable.
- Filesystem operations, calculations, state reads, DOM/UIA inspection, verification and other non-visual mechanics should stay direct and fast.
- A visible action must never weaken the verification invariant.

Other supported modes:

- `VISIBLE`: maximize visible mouse/keyboard interaction when safe.
- `FAST`: prefer direct DOM/UIA/API execution; physical input becomes fallback.

The LLM should not improvise this policy per step. A deterministic execution-policy layer chooses the method from action type, target capabilities, scene confidence and user mode.

## 3. Verification invariant

Permanent fail-closed rule:

`COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`

`ToolResult.success=True` only means the low-level tool returned normally. It is never enough to report task success.

Every side effect requires a fresh post-action observation tied to the requested postcondition. Missing, stale, ambiguous or failed evidence means `not_verified`.

## 4. Existing Operator architecture

The current canonical Operator lives under `uni/operator/` and must remain the orchestration layer. Do not create a second universal operator.

Important existing components:

- `runtime.py` — owns the shared Operator runtime.
- `planner.py` — produces structured `MissionPlan` objects from goal + scene + action catalog.
- `executor.py` — executes plans and enforces permission, STOP, observation and verification flow.
- `action_registry.py` — canonical action metadata and Planner-visible catalog.
- `input_broker.py` — exclusive physical mouse/keyboard lease and STOP generation latch.
- `perception.py` — perception priority and scene composition.
- `windows_provider.py` — semantic Windows/UIA actions.
- `browser_provider.py` / `browser_targeting.py` / `dom.py` — semantic browser control using the real BrowserSession.
- `file_provider.py` — direct filesystem operations.
- `verifier.py` — independent postcondition verification.
- `recovery.py` — bounded retry/reobserve/replan policies.

Existing low-level Windows capability remains `uni/capabilities/computer.py`. Do not duplicate `ComputerCapability`.

Existing browser runtime remains `BrowserSession`; do not start a separate blank Chromium for DOM targeting.

## 5. Current verified Windows surface

The current Windows semantic layer supports or is in active integration for:

`inspect`, `read`, `fill`, `click`, `check`, `uncheck`, `select`, `press`, `focus`, `launch`.

Recent live Windows acceptance has demonstrated:

`MissionExecutor -> fresh UIA -> semantic target -> action -> fresh observation -> filesystem/state verification -> TaskOutcome VERIFIED`.

UIA `InvokePattern` is preferred when a direct semantic action is appropriate, with physical click fallback available. `TogglePattern` is used idempotently for checkbox state, and ComboBox selection uses semantic UIA patterns.

Last known Operator verification baseline before this roadmap update:

- `tests/operator`: 151 passed, 2 skipped.
- verification invariant checker: PASS.
- strict architecture audit: 0 errors, 0 warnings.
- Windows focused semantic/live block: 10 passed.
- previously reproduced `Tcl_AsyncDelete` ActionBadge crash was eliminated on the reproducer and mixed regression.

These counts are historical evidence only. Any agent making new changes must rerun relevant tests and may not reuse these counts as proof that later code is healthy.

## 6. Visible execution design

Add a deterministic execution-policy layer rather than scattering mode checks across providers.

Planned types:

- `ExecutionMode`: `VISIBLE`, `BALANCED_VISIBLE`, `FAST`.
- `ExecutionMethod`: direct structural action, visible physical action, or safe fallback.
- `ExecutionDecision`: chosen method plus reason and requirements.
- `ExecutionPolicy`: pure/deterministic decision logic based on action spec, target, scene and configured mode.

The policy must never allow a less reliable visible action merely for appearance. If a reliable screen-space target cannot be derived, use a safe structural method or fail closed.

Visible interaction rules for `BALANCED_VISIBLE`:

- Button/menu/list item: structural targeting first, then visible cursor move + click where safe.
- Checkbox/radio: structural targeting, visible click when safe, then fresh UIA checked-state verification.
- Text field: structural targeting, visible focus, then physical typing or paste; verify with fresh value readback.
- Drag/drop, canvas, game viewport, Photoshop-like viewports: physical mouse is the normal executor, with Vision/OCR/UIA used to find/verify targets when available.
- Read-only state inspection: direct DOM/UIA/OCR, no fake mouse movement.
- Filesystem copy/move/read/write: direct filesystem provider unless the user explicitly asks to demonstrate UI workflow.
- Browser download: Playwright/browser event + fresh filesystem verification; do not simulate OS mechanics purely for show.

Visible motion should be quick and readable, typically about 150-500 ms depending on distance. No instant teleport by default, and no intentionally slow theatrical motion.

## 7. Operator event stream

Visible execution should emit provider-neutral progress events so WebUI/Telegram/desktop UI can display what UNI is doing without controlling execution.

Suggested states:

`locating -> target_resolved -> moving -> focusing -> clicking/typing/selecting -> observing -> verifying -> verified/not_verified`.

Example user-facing text:

`Ищу: кнопка "Сохранить"`
`Метод: UIA -> мышь`
`Действие: нажимаю`
`Проверка: файл существует`
`VERIFIED`

The event sink must be optional and must not become a second source of truth for task completion.

## 8. Verified Skill Memory

The long-term goal is not to memorize raw mouse coordinates. UNI should remember **verified semantic workflows**.

Three memory levels are planned:

1. **Target memory** — stable semantic identity of frequently used controls in an application.
2. **Action recipe** — a short reusable sequence such as `File -> Export -> PNG -> Save`.
3. **Verified skill** — a complete reusable workflow with context constraints, permissions, postconditions and success/failure statistics.

A skill may include:

- normalized goal/intent;
- application executable/process identity;
- window title/class or other context constraints;
- semantic target identity: source, role, name/text, automation_id and stable metadata;
- action and parameters;
- required permissions;
- explicit postcondition;
- verification strategy;
- successes, failures, consecutive verification failures;
- schema version and timestamps.

Coordinates/bounding boxes may be cached as hints for speed, but they are never sufficient identity and never authorize blind reuse.

Only a mission that ends with `TaskOutcome.status == VERIFIED` may produce or strengthen a durable skill.

## 9. Skill reuse rules

Skill reuse is a fast path before expensive replanning, not a bypass around normal execution.

Reuse flow:

`goal -> normalize -> candidate skill -> fresh context observation -> semantic target re-resolution -> ordinary MissionPlan -> ordinary permissions -> ordinary executor -> fresh verification`.

If the app/window/target no longer matches, the skill is considered stale for that attempt and UNI falls back to normal perception/planning. It must not click the last known coordinates.

The first implementation should use deterministic normalized matching rather than embeddings. YAGNI: semantic-vector retrieval can be added later only if exact/normalized matching proves insufficient.

A simple confidence score may use a bounded Bayesian estimate such as `(successes + 1) / (successes + failures + 2)`. Confidence never replaces fresh context validation or postcondition verification.

After repeated verification failures, the skill should automatically stop being a fast path. Initial policy: disable automatic reuse after 2 consecutive verification failures, then relearn through the normal planner.

## 10. Skill storage

Preferred durable store: stdlib SQLite under `runtime/operator/skills.sqlite3`.

Reasons:

- restart-safe;
- bounded/queryable rather than append-only growth;
- no new service dependency;
- easy schema versioning and migration;
- runtime data remains outside version control.

Do not promote legacy `uni/tools/trajectory_store.py` into the authoritative skill database. It may remain a legacy/reference trajectory source, but the new skill store must enforce verified-only writes itself.

## 11. Implementation roadmap

### Phase A — Execution policy foundation

Create `uni/operator/execution_policy.py` with pure deterministic policy types and tests.

Acceptance:

- `BALANCED_VISIBLE` is the default.
- read/inspect/filesystem operations remain direct;
- normal Windows click/fill/check/select prefer visible execution when a trustworthy target exists;
- `FAST` prefers structural/direct execution;
- unsafe/ambiguous physical targeting never becomes a guessed click.

### Phase B — Visible Windows executor

Create a focused visible-action component rather than putting policy into `WindowsProvider` or `ComputerCapability`.

It should consume a freshly resolved semantic UI element, use the existing `InputBroker`, human mouse movement and keyboard primitives, and return only low-level action results. Verification stays in `MissionExecutor`/`PostconditionVerifier`.

Acceptance includes button click, text focus/type, checkbox, selection, drag when supported, STOP during motion, and no physical action on ambiguous/stale targets.

### Phase C — MissionExecutor integration

Before dispatching a user-facing desktop side effect, ask `ExecutionPolicy` for a method and route through visible or direct execution accordingly. Do not introduce a second executor.

Acceptance:

- visible/direct choice is recorded in execution metadata/events;
- STOP cancels visible input promptly;
- permissions are checked before either route;
- side-effect success still requires fresh verification;
- direct and visible routes produce the same postcondition contract.

### Phase D — Browser visible interaction

Use DOM to identify the correct element first. Only perform a physical browser click/type when DOM geometry can be mapped to screen coordinates with reliable browser-window/chrome offsets and current viewport state.

If that mapping is not trustworthy, keep the structural DOM action rather than guessing a physical coordinate.

Acceptance covers normal form controls, scrolling, zoom/DPI changes, popup/tab changes and stale DOM references.

### Phase E — Progress/event stream

Add an optional operator event sink with typed events for locating, moving, acting, observing and verifying. UI layers may subscribe but must not determine completion.

### Phase F — Skill models/store

Create focused skill data models and SQLite store with schema versioning, deterministic IDs, bounded queries and verified-only write API.

Never store secrets, clipboard contents, password-field values, auth tokens or sensitive text in learned skills.

### Phase G — Verified skill learner

After a mission reaches `VERIFIED`, convert eligible semantic steps into a skill candidate and upsert it. Failed, interrupted, blocked or merely tool-successful missions must not teach durable behavior.

### Phase H — Fast skill reuse

Before LLM planning, look for a deterministic skill candidate. Revalidate app/window/semantic targets from a fresh scene and compile the skill back into a normal `MissionPlan`.

If anything is stale or ambiguous, abandon the fast path immediately and use normal planning.

### Phase I — Confidence and self-repair

Track verified successes/failures. Disable automatic reuse after repeated verification failures. A later normal-plan VERIFIED run may update/re-enable the recipe.

### Phase J — UI integration

Expose execution mode, current visible action, verification state and skill-reuse state to WebUI/Telegram only after core event contracts are stable. UI integrations are consumers, not execution owners.

## 12. Testing strategy

All behavior changes use RED -> GREEN TDD.

Required unit coverage:

- policy matrix for all execution modes;
- target ambiguity and missing bbox handling;
- direct vs visible routing;
- STOP/InputBroker behavior;
- skill verified-only persistence;
- exact context matching and stale-context rejection;
- confidence/failure disable rules;
- sensitive-field exclusion.

Required live/integration acceptance:

- isolated Windows fixture: locate -> move visibly -> click/type/check/select -> fresh UIA verification;
- MissionExecutor end-to-end with `TaskOutcome == VERIFIED`;
- STOP while cursor is moving;
- changed UI causes semantic re-resolution rather than old-coordinate click;
- saved skill survives process restart;
- second execution of a known workflow uses the skill fast path but still performs fresh verification;
- failed verification never writes or strengthens a skill.

Mandatory project gates before strong completion claims:

`C:\LLM\python312\python.exe scripts\check_verification_invariant.py`

`C:\LLM\python312\python.exe -m uni.check_architecture --strict`

Relevant pytest suites, then broader regression when shared-agent state permits.

`git diff --check`

## 13. Multi-agent ownership rules

The repository is shared and dirty. Every agent must run `git status`, inspect the current branch, and inspect the diff of each file before modifying it.

Unknown uncommitted changes belong to another agent. Do not reset, clean, restore, mass-checkout or delete them.

If a shared file has unrelated active edits, stop only that subtask and record a conflict; continue on independent files.

Current lane snapshot (must be refreshed before edits):

- **GPT UNI Night**: Operator integration, Windows/Desktop semantic actions, visible execution policy, verification/regression.
- **Hermes**: `uni/transports/**`, optional `uni/media/contracts.py`, `tests/transports/**`, Telegram gateway handoff. Do not edit these while Hermes is active.
- **DevCoord/MAWC agent(s)**: `uni/devcoord/**`, `tests/devcoord/**` and coordinator work. Do not mix Operator changes into that lane.
- **WebUI agents**: active WebUI files may contain parallel changes; consume Operator events only after contracts are stable.

## 14. Definition of done for this direction

This direction is not complete merely because UIA or mouse primitives exist. It is complete when all of the following are true:

- UNI chooses visible vs direct execution deterministically and quickly.
- The user can normally see meaningful desktop/browser interactions.
- Structural perception still provides precise target identity.
- No blind coordinate replay is used as learned behavior.
- Every side effect remains independently verified.
- Only VERIFIED workflows become durable skills.
- Reused skills revalidate context before execution and reverify afterward.
- STOP, permissions and InputBroker remain authoritative.
- Changed UI safely falls back to ordinary perception/planning.
- Relevant unit, live E2E, invariant and architecture gates are green.

## 15. Detailed documents

Design spec:
`docs/superpowers/specs/2026-09-11-uni-balanced-visible-skill-memory-design.md`

Implementation plan:
`docs/superpowers/plans/2026-09-11-uni-balanced-visible-skill-memory.md`

Agents should treat this shared roadmap as the cross-agent orientation document and the spec/plan as the detailed engineering source once those files are complete.
