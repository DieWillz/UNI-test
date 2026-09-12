# UNI Active Work Registry

> LIVE COORDINATION FILE. Every development agent MUST read this after `AGENTS.md` and `UNI_MASTER_DIRECTION.md` before changing code.
> The TOML block below is machine-readable and defines current lane ownership. Do not casually edit it; assignment changes are project-coordination events.

## Machine-readable assignments

<!-- UNI_ACTIVE_WORK_TOML_BEGIN -->
```toml
schema_version = 1

[[assignment]]
agent = "GPT UNI Coordination Gate"
task = "Fail-closed project Direction Sync Gate, persistent ACK, semantic revision, and ownership preflight"
status = "HANDOFF"
exclusive_paths = ["AGENTS.md", "docs/handoffs/UNI_MASTER_DIRECTION.md", "docs/handoffs/UNI_ACTIVE_WORK.md", "uni/direction_sync.py", "tests/test_direction_sync.py", "docs/handoffs/GPT_UNI_COORDINATION_GATE_RESULT.md"]
read_only_paths = ["uni/devcoord/**", "tests/devcoord/**", "uni/webui/**", "tests/test_admin_*", "tests/test_chat_*", "tests/test_workspace_admin_*", "uni/operator/**", "uni/transports/**", "uni/media/**"]
dependencies = ["owner directive", "MAWC integration after DevCoord lane handoff"]
updated_at = "2026-09-11T21:06:05Z"

[[assignment]]
agent = "OWNER RESERVED Autonomous Seam"
task = "Quarantine unowned dirty autonomous/control paths pending explicit Operator consolidation assignment"
status = "ACTIVE"
exclusive_paths = ["uni/agent.py", "uni/autonomous.py", "uni/autonomous_session.py", "uni/control_queue.py", "uni/xtoys_control_coordinator.py"]
read_only_paths = ["uni/operator/**", "uni/devcoord/**", "uni/transports/**", "uni/webui/**"]
dependencies = ["explicit owner assignment", "single Operator consolidation plan", "verified parity before retirement or adapter conversion"]
updated_at = "2026-09-11T21:25:54Z"

[[assignment]]
agent = "Hermes"
task = "Production Telegram transport/gateway and provider-neutral media seams"
status = "ACTIVE"
exclusive_paths = ["uni/transports/**", "tests/transports/**", "uni/media/contracts.py", "docs/handoffs/HERMES_TELEGRAM_RESULT.md"]
read_only_paths = ["uni/operator/**", "uni/devcoord/**", "uni/agent.py", "uni/event_loop.py", "uni/config.py", "uni/webui/**"]
dependencies = ["shared UNI core contracts"]
updated_at = "2026-09-11T20:20:00Z"

[[assignment]]
agent = "GPT UNI Multi-Agent Coordinator"
task = "P0 DevCoord CLI parity: expose stop-agent, force-takeover and reassign-task, then resume MAWC lifecycle work"
status = "ACTIVE"
exclusive_paths = ["uni/devcoord/**", "tests/devcoord/**"]
read_only_paths = ["uni/operator/**", "uni/transports/**", "uni/webui/**", "uni/agent.py", "uni/autonomous.py", "uni/autonomous_session.py", "uni/control_queue.py", "uni/xtoys_control_coordinator.py"]
dependencies = ["docs/handoffs/CODEX_ASTRA_P0_BASELINE_RESULT.md", "docs/handoffs/MAWC_DEVCOORD_P0_CLI_TASK.md", "explicit direction ACK after this assignment update"]
updated_at = "2026-09-11T21:48:31Z"

[[assignment]]
agent = "WebUI lane"
task = "Current WebUI/admin/chat integration work already present in the shared workspace"
status = "ACTIVE"
exclusive_paths = ["uni/webui/**", "tests/test_admin_*", "tests/test_chat_*", "tests/test_workspace_admin_*"]
read_only_paths = ["uni/operator/**", "uni/devcoord/**", "uni/transports/**"]
dependencies = ["stable Operator progress-event contract"]
updated_at = "2026-09-11T20:20:00Z"

[[assignment]]
agent = "Codex/Astra Browser Operator"
task = "P0 baseline paused after environment recovery; resume from next real failure after MAWC CLI parity fix"
status = "HANDOFF"
exclusive_paths = ["docs/handoffs/CODEX_ASTRA_P0_BASELINE_TASK.md", "docs/handoffs/CODEX_ASTRA_P0_BASELINE_RESULT.md"]
read_only_paths = ["uni/**", "tests/**", "uni/webui/**", "uni/devcoord/**", "uni/transports/**"]
dependencies = ["MAWC DevCoord CLI parity fix", "resume without repeating collection or the already-used suite-wide run"]
updated_at = "2026-09-11T21:48:31Z"

[[assignment]]
agent = "MT_DeepSeek UNI agent"
task = "P0 browser execution recovery handoff; Operator implementation ownership transferred to Codex Astra / UNI Execution Core"
status = "HANDOFF"
exclusive_paths = ["uni/event_loop.py", "uni/tools/executors.py", "tests/operator/planner_context_budget_test.py", "tests/operator/test_browser_execution_recovery.py", "docs/handoffs/GPT_UNI_BROWSER_EXECUTION_RECOVERY_RESULT.md"]
read_only_paths = ["uni/operator/**", "uni/devcoord/**", "tests/devcoord/**", "uni/webui/**", "tests/test_admin_*", "tests/test_chat_*", "tests/test_workspace_admin_*", "uni/transports/**", "tests/transports/**", "uni/media/**", "uni/agent.py", "uni/autonomous.py", "uni/autonomous_session.py", "uni/control_queue.py", "uni/xtoys_control_coordinator.py"]
dependencies = ["handoff to Codex Astra / UNI Execution Core", "preserve existing Operator work for successor review"]
updated_at = "2026-09-12T00:47:00Z"

[[assignment]]
agent = "Codex Astra / UNI Execution Core"
task = "Canonical UNI execution core: planner context budget, browser/Windows recovery, deterministic visible execution, bounded recovery/replan, STOP and progress-event contract; implementation only, tests delegated"
status = "ACTIVE"
exclusive_paths = ["uni/operator/**", "docs/handoffs/CODEX_ASTRA_EXECUTION_CORE_RESULT.md", "docs/handoffs/CODEX_ASTRA_TEST_REQUESTS.md"]
read_only_paths = ["tests/**", "uni/devcoord/**", "uni/webui/**", "uni/workspace/**", "uni/checkpoints/**", "uni/transports/**", "uni/agent.py", "uni/event_loop.py", "uni/autonomous.py", "uni/autonomous_session.py", "uni/control_queue.py", "uni/xtoys_control_coordinator.py", "uni/tools/executors.py"]
dependencies = ["owner directive 2026-09-12", "UNI_OPERATOR_SHARED_ROADMAP", "external verification agent executes TEST PROMPTS", "legacy autonomous seam remains owner-reserved"]
updated_at = "2026-09-12T00:47:00Z"

[[assignment]]
agent = "ChatGPT UNI main / Product Integration"
task = "Product integration adapters: one UNI command lifecycle, Workspace/Checkpoint aggregation, acceptance matrix, and cross-lane handoffs without duplicating core subsystems"
status = "ACTIVE"
exclusive_paths = ["uni/product_integration/**", "tests/product_integration/**", "docs/handoffs/UNI_PRODUCT_INTEGRATION_RESULT.md", "docs/handoffs/UNI_PRODUCT_INTEGRATION_OPERATOR_REQUEST.md", "docs/handoffs/UNI_PRODUCT_INTEGRATION_WEBUI_REQUEST.md", "docs/handoffs/UNI_PRODUCT_INTEGRATION_HERMES_REQUEST.md", "docs/superpowers/specs/2026-09-12-uni-product-integration-design.md", "docs/superpowers/plans/2026-09-12-uni-product-integration.md"]
read_only_paths = ["uni/operator/**", "uni/devcoord/**", "tests/devcoord/**", "uni/webui/**", "tests/test_admin_*", "tests/test_chat_*", "tests/test_workspace_admin_*", "uni/workspace/**", "tests/workspace/**", "uni/checkpoints/**", "tests/checkpoints/**", "uni/transports/**", "tests/transports/**", "uni/media/**", "uni/agent.py", "uni/event_loop.py", "uni/autonomous.py", "uni/autonomous_session.py", "uni/control_queue.py", "uni/xtoys_control_coordinator.py", "uni/tools/executors.py"]
dependencies = ["owner directive 2026-09-12", "WorkspaceService public contracts", "CheckpointManager public contracts", "Hermes transport public contract", "Codex Astra Operator public contracts"]
updated_at = "2026-09-12T01:03:03Z"
```
<!-- UNI_ACTIVE_WORK_TOML_END -->
## Current shared direction

The project-wide owner directives live in `docs/handoffs/UNI_MASTER_DIRECTION.md`.
The Operator-specific roadmap lives in `docs/handoffs/UNI_OPERATOR_SHARED_ROADMAP.md`.
Telegram implementation follows `docs/superpowers/specs/2026-09-10-uni-telegram-continuous-design.md` and its plan.
MAWC/DevCoord remains the eventual enforcement layer for task dispatch; the first sync primitive is intentionally independent so it can be integrated after the active DevCoord lane is handed off.

## Parallel execution plan

1. **GPT UNI Coordination Gate** — HANDOFF complete; shared Direction Sync primitive is ready for MAWC/DevCoord integration without touching active DevCoord files.
2. **Hermes** — continue Telegram lane until `HERMES_TELEGRAM_RESULT.md` exists and targeted tests are green.
3. **MAWC DevCoord lane** — continue its current lifecycle/lease/scheduler work; do not absorb Operator or Telegram behavior.
4. **WebUI lane** — continue existing admin/chat work; integration with Operator progress events happens only after the Operator event contract is stable.
5. After the DevCoord handoff, integrate the shared direction-sync gate into MAWC task dispatch so stale agents cannot receive new work.

## Ownership rules

- Unknown uncommitted changes belong to another agent.
- `exclusive` ownership means another agent must not modify matching paths without an explicit handoff or conflict resolution.
- A read-only path may be inspected but not modified by that assignment.
- If work needs a foreign path, record a conflict instead of editing through it.
- Assignment changes require updating the TOML block and re-running agent synchronization.

## Required startup sequence

Every coding agent must: read `AGENTS.md`; read `UNI_MASTER_DIRECTION.md`; read this file; read its subsystem spec/handoff; run `git status`; acknowledge the current direction revision; and check intended paths against ownership before editing.

## Assignment: DevCoord / MAWC lane owner

STATUS: ACTIVE

TASK:
Develop and stabilize Multi-Agent Workspace Coordinator / Development Coordinator: sessions, leases, scheduler/dispatcher, runner, verification lifecycle, integration, workspace monitoring, concurrency and security.

PRIMARY OWNERSHIP:
- currently modified `uni/devcoord/**`
- currently modified/new `tests/devcoord/**`
- MAWC specs/plans

INTEGRATION REQUEST FROM GPT UNI Coordination Gate:
- consume master-direction/work revisions
- require agent acknowledgement before assigning/starting new work
- mark stale agents and block new assignment until resync
- reuse existing resource lease system for file/lane ownership

Until this lane hands off or target files are explicitly released, GPT UNI Coordination Gate will not overwrite its dirty files.

## Assignment: Codex/Astra Browser Operator

STATUS: ACTIVE (P0 BASELINE / ENVIRONMENT ONLY)

TASK:
Repair the stale `comtypes` UIAutomation typelib cache, restore pytest collection, and classify remaining failures without feature work.

OWNERSHIP / SAFETY:
- writable handoff files only: `CODEX_ASTRA_P0_BASELINE_TASK.md`, `CODEX_ASTRA_P0_BASELINE_RESULT.md`
- `uni/**` and `tests/**` remain read-only; any source/test write requires an explicit ownership transfer
- previous Browser Operator handoff remains historical reference at `docs/handoffs/ASTRA_BROWSER_OPERATOR_RESULT.md`

## Coordination update protocol

When an agent starts, stops, blocks, completes, or transfers a lane, update only the corresponding assignment block and preserve other agents' blocks.

Every active agent should record: STATUS, TASK, PRIMARY OWNERSHIP, READ-ONLY/CONFLICT areas, dependencies, and acceptance criteria.
