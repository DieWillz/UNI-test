# UNI Execution Core verification requests

Implementation agent does not execute these commands. Status: NOT_VERIFIED.
All requests: AGENT: UNI Verification Agent. Read current AGENTS.md, Master Direction, Active Work and Execution Core result; ACK your own registered identity. Obtain ownership before adding/updating tests. Do not modify production files anywhere under uni/**, configuration, dependency versions, verification checks, or another lane's tests. No full suite. If a requested test file is absent, report/add the specified focused regression only after ownership is granted; do not silently skip it. On failure report root cause, exact nodeid, command, exit status and bounded traceback to Codex Astra; do not repair production.

## TEST PROMPT #1 — planner budget

FILES TO TEST: uni/operator/planner.py, uni/operator/context_budget.py; existing tests/operator/test_planner.py, tests/operator/test_planner_catalog.py. Add tests/operator/test_context_budget.py with ownership.
DO NOT MODIFY: all uni/** production files.
RUN from C:\LLM\UNI:
`C:\LLM\python312\python.exe -m pytest -q --tb=short --maxfail=1 tests/operator/test_context_budget.py tests/operator/test_planner.py tests/operator/test_planner_catalog.py`
SCENARIOS: 5120 context; large Cyrillic goal, scene and catalog; repeated invalid JSON; failed attempt context; invalid budget configuration; goal alone exceeds budget; desktop/browser/file goals; scene serialization remains valid and does not mutate input. Use a fake brain; record every outgoing request. No real LLM/network/browser.
EXPECTED: every request, including format repair, respects the configured counter plus output/header reservation; full goal is preserved; mandatory state/postconditions are never silently removed; oversized essential input stops before brain.chat; compact allowed action schemas retain required argument names.
IF FAILED: return exact evidence and root cause, production unchanged.
