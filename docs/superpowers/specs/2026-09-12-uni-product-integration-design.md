# UNI Product Integration Design

> Owner-approved directive: 2026-09-12. This document records the product-integration contract before production implementation.

## Goal

Present one UNI product behavior across WebUI chat, Telegram, voice and desktop/CLI without creating another brain, planner, executor, Operator or coordinator.

Canonical execution remains the existing Operator pipeline:
`command -> acknowledgement -> mini-plan -> Operator -> runtime progress -> independent verification -> VERIFIED / NOT_VERIFIED`.

## Ownership boundaries

Product Integration may add only adapter/projection code outside ACTIVE lanes.
`uni/operator/**`, `uni/devcoord/**`, `uni/webui/**`, `uni/transports/**`, `uni/workspace/**`, `uni/checkpoints/**` and the owner-reserved autonomous seam are consumed read-only through public contracts.

Cross-lane changes are delivered as explicit handoff requests to the owning agent.
## Product adapter layer

Create `uni/product_integration/` as a composition/adaptation layer, not an orchestration core.
It may define neutral request/result/progress projections and Protocols for an existing command pipeline, but it must not plan actions or execute side effects itself.

Ingress adapters normalize text from WebUI/CLI, Telegram `InboundMessage`, and STT output into the same command request shape.
Egress adapters project acknowledgement, plan, progress, replan and final outcome into transport/UI-safe messages.

TTS is best-effort output only. A TTS failure is recorded independently and never replaces or changes the execution outcome.
A spoken success phrase is allowed only when the underlying final task status is VERIFIED.
## Lifecycle projection

The integration layer may surface only runtime-backed lifecycle states:
`acknowledged`, `plan_available`, `progress`, `replan`, `verifying`, `verified`, `not_verified`, `stopped`, `blocked`.

Acknowledgement may be emitted immediately from ingress acceptance because it describes receipt, not task completion.
The mini-plan must be the actual Operator plan/public plan projection when available; no invented placeholder steps may be represented as runtime truth.
Progress and replan events must originate from the Operator public event contract. Until Codex Astra publishes that contract, Product Integration reports the capability as unavailable rather than synthesizing events.
Final status is derived from the canonical task outcome only.
## Workspace and checkpoints

Use `WorkspaceService` unchanged. Product Integration supplies source adapters that map external DevCoord snapshots and CheckpointManager data into `AgentWorkspaceView`, `TaskWorkspaceView`, and `CheckpointView`.

Each source is isolated. A temporary failure in agents, tasks, checkpoints or revision data must not crash the whole overview; failed sections become empty data plus explicit source-status/blocker metadata in the product projection.

Never synthesize 100% progress. `owner_verified` remains independent from tests/agent verification.
Checkpoint UI integration is read-only in this phase: list, inspect and prepare restore plan. No destructive restore and no Project Known Good creation from a dirty workspace.
## Safe admin and settings handoff

Because WebUI is an ACTIVE exclusive lane, Product Integration does not edit its files directly.
The WebUI owner must remove all page-load/navigation POST side effects. Read-only rendering and GET probes may run on view; restart, test-all, Dorch/device commands, mouse, microphone, camera and process-kill operations require an explicit user click.

Settings descriptions must explain behavioral effect rather than restating field names. UI must track dirty state, require Save/Apply where persistence is needed, report success/error, and reload persisted values to verify the save.
The `config.yaml.tmp -> config.yaml` PermissionError must be fixed with a safe atomic-save fallback/replace strategy without requiring elevated admin rights where avoidable.
## Acceptance matrix

Maintain a product acceptance matrix with columns:
`USER SCENARIO`, `CURRENT PATH`, `EXPECTED PATH`, `BLOCKER`, `OWNER`, `TEST STATUS`.

Required scenarios: open application, type text, save file, open site, browser interaction, multi-step task, STOP, replan after error, resume, Telegram -> UNI, voice -> UNI, visible mouse action, verified result.

Operator-internal blockers are never repaired in this lane. They become precise Codex Astra handoff requests containing the missing public contract or failing scenario.

## Verification

Use RED -> GREEN tests only for `tests/product_integration/**`. Do not run full pytest.
Run targeted Product Integration tests, verification invariant checker, architecture checker when safe, compile/import checks, and `git diff --check` on owned paths.
No transport HTTP success, TTS success, process existence, test pass or UI response may be promoted into user-task success.