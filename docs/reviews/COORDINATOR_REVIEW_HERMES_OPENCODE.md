# Coordinator review of Hermes OpenCode comparison

Status: Accepted as evidence with binding corrections

Date: 2026-07-31

The factual findings in `HERMES_OPENCODE_COMPARISON.md` are accepted. The
OpenCode implementation is reference material and must not be merged into the
canonical package.

## Binding corrections

1. Canonical action names remain `capability.action` under ADR-0002. Removing
   dots is not an allowed repair. ROUTER-002 must resolve the exact full dotted
   name through the Registry.
2. Dependency resolution must follow ADR-0004 exactly: the LLM emits local
   integer `step` references, then Planner allocates Action UUIDs and performs
   two-pass `step -> Action.id` resolution. Pre-generating IDs for the LLM or
   passing LLM-local step numbers to TaskQueue is not allowed.
3. Verification is not represented by a bare boolean. Under ADR-0004, an absent
   `VerificationResult` means `not verified`, not success. A verification
   attempt that cannot parse or obtain evidence must not be accepted as goal
   progress.
4. Error classification must use the canonical structured `ErrorType`. String
   matching may exist only as a bounded legacy adapter at an exception boundary;
   it is not the Planner's source of truth and unknown errors are not silently
   assumed transient.
5. Reuse only the separation between screenshot capture and vision analysis.
   Binary screenshots must travel by bounded artifact reference, not through
   `AgentContext` as an unbounded base64 string.
6. `mark_completed` is a useful operation, but the OpenCode queue implementation
   is not reusable as-is. Completion, failure, running ownership, deadlock, and
   replan clearing must be specified and tested together.
7. The state-machine and RoleLoader are candidates for separate bounded tasks,
   not direct copy operations. Role paths must be independent of process CWD.

## Coordination decision

- No new umbrella ADR or `.hermes/plans` source of truth is created.
- DeepSeek must use both reviews as evidence when completing PLAN-001 and
  PLAN-VECTORS-001.
- Qwen continues with CORE-002, followed by ROUTER-002.
- Hermes remains the independent local verifier and does not implement the
  planner or router under the audit task.
- OpenCode integration remains blocked until those prerequisites are accepted.
