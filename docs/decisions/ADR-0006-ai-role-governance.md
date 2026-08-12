# ADR-0006: AI role governance without Claude

Status: Accepted

## Context

Claude is no longer available for continued UNI work. The project still needs
architecture drafting, implementation feasibility checks, independent review,
and final arbitration.

Allowing one model to design, implement, review, and accept the same change
would recreate the divergence that the coordination layer was introduced to
prevent.

## Decision

Responsibilities are reassigned as follows:

- **Codex / Coordinator-Arbiter**
  - owns final architecture decisions;
  - accepts or rejects ADRs;
  - controls task status and allowed paths;
  - reviews evidence from DeepSeek and Qwen;
  - publishes accepted repository state.
- **DeepSeek / Algorithms and Architecture Analyst**
  - drafts algorithm specifications and architecture amendments;
  - creates adversarial test vectors and development skills;
  - reviews Qwen and OpenCode output;
  - does not accept its own ADR/specification;
  - does not write runtime Python without a separate implementation task.
- **Qwen / Python Implementation Engineer**
  - performs feasibility review of Proposed contracts;
  - implements only Accepted contracts;
  - writes unit tests and compatibility reports;
  - does not change or accept architecture;
  - does not review its own implementation as final reviewer.
- **OpenCode / Lead Integration Engineer**
  - integrates accepted contracts, router, planner, and event loop;
  - reports integration conflicts instead of changing contracts locally.
- **Hermes / Local Runtime Auditor**
  - reproduces defects against the canonical local package and installed runtime;
  - may implement only an explicitly approved, path-bounded hotfix task;
  - adds regression tests and records the exact local dependency versions used;
  - does not change contracts, accept ADRs, or perform broad cleanup;
  - verifies integrated changes independently after Qwen or OpenCode work.

## Approval flow

```text
DeepSeek draft/specification
          ↓
Qwen feasibility review
          ↓
Coordinator decision / Accepted ADR
          ↓
Qwen implementation
          ↓
DeepSeek adversarial review + Hermes local runtime verification
          ↓
Coordinator acceptance
          ↓
OpenCode integration
```

For implementation primarily authored by DeepSeek, Qwen provides the
independent review instead.

## Consequences

- Claude is removed from all blocking dependencies.
- `CORE-001` and `ROUTER-001` are completed by coordinator amendments to the
  existing Claude drafts, informed by DeepSeek and Qwen reviews.
- No model may mark its own output Accepted or Complete.
