# Initial review: DeepSeek specifications and Qwen proposed implementation

Date: 2026-07-31

## Decision

- DeepSeek analytical output: useful draft, not complete.
- DeepSeek previous Python implementation: rejected.
- Qwen proposed code: rejected as implementation input; implementation plan is
  accepted as a starting checklist.
- `CORE-002` and `ROUTER-002` remain blocked until ADR-0004/0005 are Accepted.

## DeepSeek blocking findings

1. DS-005/DS-006 contain examples and `...`, not the required complete
   machine-readable test vectors.
2. `Action.id` example `browser.navigate_1` is not globally stable across
   plans; ID generation must follow ADR-0004.
3. Invalid priority must be rejected by contract validation, not silently
   coerced to `1`.
4. Verification failure must not automatically imply repeating the original
   action; reobserve/reverify and action retry are distinct decisions.
5. Context compression cannot retain all permanent failures forever while
   claiming a fixed bound.
6. Verification requirements need manifest/policy metadata rather than
   subjective "significant action" wording.
7. Proposed specifications must be revised after final ADR-0004/0005.

## Qwen blocking findings

### Contracts

1. `Task.id == Action.id` is not enforced. The proposed test explicitly creates
   `task_1` with `action.id=act_1` and therefore proves the invariant is broken.
2. `VerificationResult` is missing.
3. `ActionResult` timestamp, bounded data rule, and artifact reference are
   missing.
4. `Observation.source` and artifact reference are missing.
5. `AgentContext` does not represent the accepted ownership/state fields.
6. Task retry fields and exact status transitions are incomplete.
7. Tests do not cover the required invariant matrix.

### Manifest and registry

1. `parameters: dict[str, Any]` is a second hand-maintained schema, not a
   Pydantic parameter-model source of truth.
2. `name` plus separate `prefix` creates two owner identities that can drift.
3. Prefix mismatch validation is ineffective because the full name is built
   from the same prefix being checked.
4. Registration is not atomic; a later failing action can leave earlier action
   entries in the index.
5. Manifest validation and JSON Schema derivation are incomplete.

### Router

1. Parameter validation is explicitly not implemented.
2. A wrong `action_id` returned by a capability is silently rewritten, hiding
   a contract violation; this must produce a defined internal failure.
3. Unknown exceptions default to transient, enabling unsafe retry of
   non-idempotent actions.
4. Router-produced results omit timestamp/verification fields required by the
   proposed contract.
5. Proposed tests do not cover invalid parameter models or atomic registration.

### Scope

Proposed `uni/utils/error_classifier.py` conflicts with the no-utils-dump
convention and was not an allowed path. Proposed `uni/planner/task_queue.py`
also conflicts with the existing `uni/planner.py` module layout and is outside
the task.

## Required next outputs

DeepSeek:

- revise specifications after Accepted ADRs;
- provide actual files rather than chat-only snippets;
- provide complete YAML vectors with no placeholders.

Qwen:

- provide feasibility findings only until ADR acceptance;
- after acceptance, implement exact contracts and router in the assigned branch;
- run tests rather than provide expected results for the coordinator to run.
