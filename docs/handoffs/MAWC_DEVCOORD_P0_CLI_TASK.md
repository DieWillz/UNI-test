# MAWC DevCoord — P0 CLI parity

AGENT: `GPT UNI Multi-Agent Coordinator`

GOAL: fix the first real post-collection baseline failure without broad refactor.

## Verified failure

`tests/devcoord/test_cli_workspace.py::test_stop_takeover_and_reassign_commands` fails because `uni/devcoord/__main__.py` does not register `stop-agent`.
Static inspection also confirms `force-takeover` and `reassign-task` are absent from parser/dispatch while matching service methods already exist.

## Scope

Modify only what is necessary in `uni/devcoord/__main__.py` and, only if required, its existing DevCoord CLI test.
Do not change service semantics unless the existing test proves a real service bug.
Do not touch Operator, WebUI, Telegram, autonomous/control paths, or unrelated DevCoord code.

## Required implementation

Add CLI parser entries and dispatch for `stop-agent`, `force-takeover`, and `reassign-task` using existing `DevelopmentCoordinatorService` methods and `_emit`.
Preserve current `--db` behavior. For `reassign-task`, expose the existing optional TTL only if needed by the current service contract; do not invent new options.

## Verification budget

First run only `tests/devcoord/test_cli_workspace.py::test_stop_takeover_and_reassign_commands`.
If green, run `tests/devcoord/test_cli_workspace.py` and the smallest directly related service test(s).
Do not run the full suite; Astra resumes baseline afterward.

RESULT: update `docs/handoffs/MAWC_DEVCOORD_P0_CLI_RESULT.md` with changed files, exact checks, and remaining blocker only.