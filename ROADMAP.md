# UNI Consolidation Roadmap

## Phase 0 — Governance

- [x] Select canonical source.
- [x] Mark variants as reference-only.
- [x] Add architecture rules, ADR process, task registry, and audit script.

## Phase 1 — Canonical contracts

- [ ] Accept contract ADR.
- [ ] Implement one `Action`, `ActionResult`, `Observation`, and `AgentContext`.
- [ ] Add contract tests.
- [ ] Remove or adapt duplicate result types.

## Phase 2 — Routing

- [ ] Define capability manifest and registry contract.
- [ ] Implement `CapabilityRouter`.
- [ ] Migrate every tool to `capability.action`.
- [ ] Make every execution path return `ActionResult`.

## Phase 3 — Planning

- [ ] Validate LLM plans against registered manifests.
- [ ] Use stable plan step IDs and translate dependencies.
- [ ] Add deterministic retry and bounded replan decisions.

## Phase 4 — One event loop

- [ ] Introduce `AgentContext`.
- [ ] Integrate Planner, TaskQueue, Router, verification, and recovery.
- [ ] Add human-in-the-loop.
- [ ] Emit structured Thinking Mode events.

## Phase 5 — MVP verification

- [ ] Install a reproducible development environment.
- [ ] Pass unit and integration tests.
- [ ] Pass a mocked YouTube scenario.
- [ ] Pass the real local YouTube scenario.

No new capability is added before Phase 4 is complete unless it is required by
the MVP acceptance scenario.
