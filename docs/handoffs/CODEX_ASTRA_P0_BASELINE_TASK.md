# Codex Astra — P0 Test Baseline

AGENT: `Codex/Astra Browser Operator`

STATUS: ASSIGNED BY PROJECT COORDINATOR

GOAL: restore a trustworthy pytest baseline before further cross-cutting UNI work. Do not implement new features in this task.

## Required preflight

Read once: `AGENTS.md`, `docs/handoffs/UNI_MASTER_DIRECTION.md`, `docs/handoffs/UNI_ACTIVE_WORK.md`, this file.
Then run `git status --short`, ACK the current direction revision, and check ownership for every repo path before any write.
Unknown dirty changes belong to other agents. No reset/clean/stash/rebase/merge/cherry-pick/mass restore.

## Known blocker already reproduced

`pytest --collect-only -q` reached 819 collected tests but ended with 21 collection errors.
The repeated root error is `ImportError: Typelib different than module` from generated `comtypes.gen.UIAutomationClient`.
Cached wrapper mtime: `1786480634.807760`.
Current `C:\Windows\System32\UIAutomationCore.dll` mtime: `1788923752.9637759`.
Strict architecture audit is currently `0 errors, 0 warnings`.

## Phase 1 — environment repair only

Treat generated `comtypes/gen` files as environment cache, not UNI source.
Back up stale UIAutomation generated modules before regeneration; do not delete unrelated comtypes cache.
Regenerate/re-import UIAutomation typelib with the existing Python environment.
Do not change UNI production code merely to mask a stale generated typelib.
## Phase 2 — economical verification

1. Run one import probe for `comtypes.gen.UIAutomationClient` / `uni.capabilities.computer`.
2. Run `pytest --collect-only -q` once.
3. If collection is clean, run only tests associated with the first real failure groups.
4. Run the full suite at most once after targeted blockers are understood/fixed; do not loop full pytest.
5. Keep output bounded: `-q --tb=short --maxfail=1` while diagnosing.

If collection still fails for a reason unrelated to stale comtypes cache, identify the first root cause before changing code.

## Source-write policy

This assignment does NOT grant broad production ownership.
Do not modify `uni/operator/**`, `uni/event_loop.py`, `uni/autonomous.py`, `uni/tools/**`, `uni/webui/**`, `uni/devcoord/**`, `uni/transports/**`, ControlQueue/Dorch, or their tests in this task.
If a repo code change is truly required to make collection deterministic, stop and report the exact proposed files and root cause for coordinator ownership allocation.

## Required result

Create/update `docs/handoffs/CODEX_ASTRA_P0_BASELINE_RESULT.md` with only:
- root cause;
- environment actions performed;
- collection count/result;
- first remaining real failures, if any;
- exact repo files that would need changes next;
- commands actually run.

Do not claim project health from collection alone. Do not start execution-pipeline migration in this task.