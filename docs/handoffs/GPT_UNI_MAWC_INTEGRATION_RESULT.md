# GPT UNI MAWC Integration Result

AGENT:
GPT UNI MAWC Integration

## CHANGED

- `uni/devcoord/direction_gate.py` — MAWC adapter over the existing project-wide `uni.direction_sync.DirectionSyncGate`; no second lock/coordinator system.
- `uni/devcoord/workspace_models.py` — direction ACK/sync/stale session data plus acceptance items, blockers and owner-verification task data.
- `uni/devcoord/scheduler.py` — fail-closed direction/ownership gate before new reservation and lease claim.
- `uni/devcoord/dispatcher.py` — propagates the same Direction Sync dependency into normal dispatch/worktree preparation.
- `uni/devcoord/service.py` — sync-aware assignment/reassignment, ACK facade and structured coordination status.
- `uni/devcoord/__main__.py` — canonical MAWC CLI wiring to project DirectionSyncGate and `ack-direction`; existing owner lifecycle commands exposed.
- `tests/devcoord/test_mawc_direction_integration.py` — RED -> GREEN integration coverage for required behavior.
## TESTED

TDD was used for this integration.

- RED: scheduler tests first failed because MAWC had no Direction Sync dependency.
- RED: dispatcher/service integration then failed because they could bypass the protected scheduler path.
- GREEN: `C:\LLM\python312\python.exe -m pytest tests\devcoord\test_mawc_direction_integration.py tests\devcoord\test_cli_workspace.py -q` -> `24 passed`.
- Canonical DevCoord + project Direction Sync: `C:\LLM\python312\python.exe -m pytest tests\devcoord tests\test_direction_sync.py --ignore=tests\devcoord\test_direction_sync.py -q` -> `155 passed`.
- Full `tests/devcoord` -> `140 passed, 1 failed`; the only failure is the pre-existing stale `tests/devcoord/test_direction_sync.py` importing nonexistent `uni.devcoord.direction_sync`.
- `C:\LLM\python312\python.exe -m uni.check_architecture --strict` -> `0 errors, 0 warnings`.
- `C:\LLM\python312\python.exe scripts\check_verification_invariant.py` -> PASS.
- Scoped `git diff --check` and `py_compile` for the touched DevCoord production modules -> exit 0.
## MAWC DATA CONTRACT

`MawcDirectionCoordinator.snapshot()` returns one structured state for later `UNI_ACTIVE_WORK.md` generation and Admin UI consumption:

- `agents`: session identity, `direction_revision_ack`, `direction_synced_at`, `last_heartbeat`, `last_updated`, `current_task`, computed progress, owned paths, status, stale flag and blockers.
- `tasks`: persisted MAWC task records including acceptance items and owner-verification state.
- `assignments`: task/session/state bindings.
- `leases`: the existing MAWC resource leases; Direction Sync does not create parallel lock files.
- `progress`: per-task `passed`, `total`, computed integer `percent`, `owner_verified`, and `user_confirmed_percent`.
- `updated_at`, `direction_revision`, `ack_revision`, `stale`, `blockers`.

Agent coordination statuses are: `SYNC_REQUIRED`, `READY`, `ACTIVE`, `VERIFYING`, `BLOCKED`, `STALE`, `DONE`.
`DONE` is lifecycle completion only and does not mean owner verified.
## INTEGRATION POINTS

- Agent registration/ACK: `DevelopmentCoordinatorService.acknowledge_direction()` -> `MawcDirectionCoordinator.acknowledge()` -> existing `DirectionSyncGate.acknowledge()`.
- New-task selection: `TaskScheduler.ready_tasks()` filters stale/not-ACKed/foreign-owned work.
- Final reservation: `TaskScheduler.reserve_next()` rechecks direction on the fresh session/task before claiming existing MAWC leases.
- Normal execution path: `TaskDispatcher` owns a sync-aware scheduler, so worktree creation cannot bypass direction checks.
- Manual owner path: `assign_task`, `assign_next`, and `reassign_task` enforce the same direction dependency; reassignment checks before old leases are released.
- Heartbeat/stale handling remains in `AgentSessionManager`; stale leases remain present and conflicting until controlled takeover/release.
- CLI canonical DB under `.uni-dev/coordination/workspace.sqlite` automatically wires Master Direction, Active Work, and `.uni-dev/coordination/direction_ack.json`.
- `ack-direction <session_id>` records the external semantic revision and mirrors it into the MAWC session.
## RESULT

MAWC now consumes the single project-wide Direction Sync primitive rather than inventing a second coordinator or lock system. A missing/stale ACK, stale heartbeat, foreign ACTIVE ownership, or conflicting existing lease prevents new work. A revision change does not destroy an already-held lease or forcibly interrupt a current safe step; the session must resync before receiving new work.

Progress is derived from acceptance items (`passed / total`). Even when every acceptance item passes, `owner_verified` remains a separate fact and user-confirmed progress is capped below 100 until owner verification.

The existing protected `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED` invariant is unchanged.

## REMAINING

- `tests/devcoord/test_direction_sync.py` is stale foreign-lane baseline created before this integration. It expects a parallel module `uni.devcoord.direction_sync` with an incompatible API. Do not satisfy it by creating a second Direction Sync implementation; migrate/remove that test under explicit ownership, using canonical `tests/test_direction_sync.py` plus this MAWC integration suite instead.
- The shared working tree still contains many unrelated dirty changes from other active lanes. No bulk staging, reset, clean, restore, or cross-lane commit was performed.
- Owner verification of the product behavior is still separate from automated verification; no task is marked owner-verified by this integration.