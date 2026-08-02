# Coordinator review: CORE-001 and ROUTER-001

Date: 2026-07-31

Reviewed:

- `ADR-0004-runtime-contracts.md` — Proposed
- `ADR-0005-capability-router.md` — Draft

## Decision

- `CORE-001`: Changes requested. Not Accepted yet.
- `ROUTER-001`: Changes requested. Remains Draft.
- `CORE-002` (Qwen): remains blocked.

The overall direction is approved: Pydantic boundary models, one
`ActionResult`, stable action IDs, two-pass dependency resolution, manifests,
and dotted action names.

## Blocking corrections for ADR-0004

### 1. Make every schema implementable without interpretation

Define the actual named enums/models, not prose-only object shapes:

- `ActionStatus`
- `ErrorType`
- `TaskStatus`
- `VerificationResult`

State the exact invariant matrix for `ActionResult`, including:

- success requires `error_type=none` and `error=None`;
- failure/timeout/cancelled require an error or reason;
- timeout requires `error_type=timeout`;
- when verification may be present and what `checked` means.

### 2. Specify enforceable bounds

Replace `max ~2000 chars` with an exact value.

`ActionResult.data: Any` cannot be described as bounded without a rule. Choose
an enforceable contract, for example JSON-serializable inline data with a
serialized size limit, otherwise an artifact/reference field.

### 3. Resolve Pydantic runtime references in AgentContext

`AgentContext` contains `TaskQueue` and `WorkingMemory` runtime objects. State
whether they are:

- excluded Pydantic fields with arbitrary types enabled; or
- removed from the Pydantic data model and injected into a separate runtime
  services container.

Qwen must not invent this decision.

### 4. Resolve Task identity as a schema invariant

`Task.id == Task.action.id` needs an exact implementation contract:

- either remove stored `Task.id` and expose it as a property; or
- retain it and require a model-level validator.

Also specify how `cancelled` ActionResult maps to TaskStatus, which currently
has no cancelled state.

### 5. Correct task scope consequences

CORE-002 is allowed to change only:

- `uni/contracts.py`
- `tests/unit/test_contracts.py`

Therefore ADR-0004 must not assign capability signature migration or a
mechanical rename pass to CORE-002. Those changes belong to a separate
migration/router task or INTEGRATE-001.

CORE-002 implements contracts and tests only.

### 6. Clarify unknown exception classification

Do not require every unknown capability exception to be classified as
transient. Define a conservative default and allow known exception mapping.
Retry policy must not repeat a potentially non-idempotent action merely because
an unexpected programming error was labeled transient.

## Blocking corrections for ADR-0005

### 1. Capabilities must not invoke the router

The proposed rule allowing a capability to issue another `Action` through the
router violates the intended dependency direction and permits recursive
capability orchestration.

Required rule:

- a capability never calls another capability, directly or through the router;
- multi-capability orchestration belongs to Planner/EventLoop;
- a capability may use its own external adapter/library, but not another UNI
  capability instance;
- XToys browser/vision composition must move to a workflow/plan or use an
  XToys-owned external adapter.

The router dispatch direction is one-way:

`EventLoop -> CapabilityRouter -> Capability`.

### 2. Resolve parameter schema source of truth

The `params_schema` open question blocks implementation. Select one canonical
source that can also generate the OpenAI tool schema. Recommended:

- each `ActionSpec` references a Pydantic params model;
- validation uses that model;
- JSON schema for LLM/tool exposure is derived from the same model;
- no separately maintained schema dictionary is allowed.

### 3. Define manifest and registration models

Specify whether `CapabilityManifest` and `ActionSpec` are canonical Pydantic
contracts and where they are implemented. Define duplicate action-name
behavior and startup failure semantics.

At minimum, registration must reject:

- duplicate capability names;
- duplicate full action names;
- prefix/owner mismatch;
- invalid dotted names;
- empty action collections where disallowed.

### 4. Complete router result invariants

Every router-produced result must include the input `action.id` as
`action_id`, plus a timestamp, and must conform to ADR-0004's invariant matrix.

### 5. Separate idempotency from automatic retry permission

Clarify that `idempotent` is planner metadata, not independent authorization
for the router to retry. The router dispatches once. PLAN-001 owns retry
decisions and must consider verification and error classification.

## Non-blocking recommendations

- Prefer UUID as the internal `Action.id` type, serialized as a string.
- Use a UTC datetime rather than an untyped float timestamp if compatibility
  permits; otherwise define Unix seconds precisely.
- Reset and prior-plan dependency behavior belongs in PLAN-001, as Claude
  correctly noted.
- Atomic WorkingMemory writes should be a separate scoped task, not CORE-002.

## Required resubmission

Claude should return revised full files:

- `docs/decisions/ADR-0004-runtime-contracts.md` with status `Proposed`;
- `docs/decisions/ADR-0005-capability-router.md` with status `Proposed` only
  after ADR-0004 corrections are incorporated.

No Python implementation is requested.
