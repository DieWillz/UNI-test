# Dorch / XToys Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize UNI and make Dorch autonomous control flow through one Intiface-backed queue without per-command owner confirmation, with truthful speech/action synchronization.

**Architecture:** All device motion goes through `ControlQueue -> ToyControlCoordinator -> IntifaceBridge`. Persistent config grants autonomy; STOP, max intensity, and device/connection presence remain hard runtime gates. Speech is tied to queue execution events instead of an independent monologue timeline.

**Tech Stack:** Python 3.12, asyncio, pytest/pytest-asyncio/pytest-timeout, Buttplug/Intiface, stdlib WebUI, Electron/JS launcher.

**Spec:** `docs/superpowers/specs/2026-09-04-dorch-stabilization-design.md`

## Global Constraints
- Work in the existing `C:\LLM\UNI` working tree; preserve the pre-change snapshot.
- Never reintroduce browser/DOM control as a physical device path.
- Keep emergency STOP latched until manually reset and keep `max_intensity` as a hard ceiling.
- No success/physical-verification claim without evidence beyond command acceptance.
- Use TDD for every production behavior change.
### Task 1: ControlQueue correctness and autonomous authorization
**Files:** Modify `uni/control_queue.py`, `uni/xtoys_control_coordinator.py`, `uni/capabilities/xtoys.py`, `uni/agent.py`; create `tests/test_control_queue.py`; update XToys tests.
**Produces:** queue replacement semantics, config-based autonomous gate, no `verified_physical` per-action requirement.
- [ ] Write failing tests for `replace_all`, `replace_pending`, STOP, max limit, no-device rejection, and autonomous positive command with enabled config.
- [ ] Run targeted tests and confirm failures match current defects.
- [ ] Fix replacement horizon calculation and remove `verified_physical` from autonomous permission predicates.
- [ ] Keep coordinator/bridge presence and emergency-stop gates fail-closed.
- [ ] Run ControlQueue/coordinator/XToys tests to green.

### Task 2: Device-step speech synchronization
**Files:** Modify `uni/control_queue.py`, `uni/autonomous.py`; create `tests/test_dorch_speech_sync.py`.
**Produces:** execution events for step started/applied/failed and speech emitted from applied state.
- [ ] Write failing tests proving speech never precedes a successful coordinator command and failure speech does not claim motion.
- [ ] Add a queue event callback carrying step id, target/commanded value, status, and reason.
- [ ] Route autonomous speech generation through those execution events; remove independent device-claim timing.
- [ ] Verify STOP cancels pending speech/device state and tests pass.
### Task 3: WebUI Dorch cleanup
**Files:** Modify `uni/webui/server.py`, `uni/webui/js/chat-controls.js`, relevant HTML/CSS if confirmation controls exist, `tests/test_chat_controls.py`, `tests/test_chat_ui.py`.
**Produces:** one Dorch status source, no physical-confirm button/API dependency, accurate no-device state.
- [ ] Write failing tests for config-authorized autonomous session and absence of per-action confirmation UI.
- [ ] Remove/retire `/api/intiface/confirm-physical` from the active flow and remove the confirmation button behavior.
- [ ] Make session status expose Intiface connected/devices, queue current/pending, commanded value, STOP, and last error from canonical state.
- [ ] Fix role-switch failure test lifecycle so the UI suite terminates.
- [ ] Run chat/UI/API tests to green.

### Task 4: Legacy autonomous/XToys test migration
**Files:** Modify `tests/integration/test_autonomous.py`, `tests/fasttrack/test_xtoys_dom.py`; minimize dead branches in `uni/capabilities/xtoys.py` where safe.
**Produces:** regression tests that exercise coordinator/queue architecture rather than removed DOM behavior.
- [ ] Replace DOM slider expectations with coordinator/Intiface doubles.
- [ ] Replace `xtoys.ramp_intensity` autonomous expectations with queue/coordinator behavior.
- [ ] Verify browser session is never touched for device motion.
- [ ] Run migrated tests and surrounding fasttrack/integration suites.
### Task 5: General stabilization defects
**Files:** Modify `uni/event_loop.py`, `pytest.ini` and/or development environment; tests as needed.
**Produces:** screen-watch runtime fix and bounded test execution.
- [ ] Add a regression test for the screen-watch observation path that currently reaches `time.time()`.
- [ ] Add the missing `time` import and verify the regression passes.
- [ ] Ensure `pytest-timeout` is installed in the active Python environment and `timeout=90` is recognized.
- [ ] Run the previously hanging UI scenario and confirm the process terminates.

### Task 6: Provider-aware launcher
**Files:** Modify `scripts/launcher.js`; add/update `tests/test_architecture.py` or launcher-focused tests.
**Produces:** LM Studio mode skips embedded llama; embedded mode launches/watches it.
- [ ] Write a static/unit test for provider-dependent launcher behavior.
- [ ] Parse `brain.llm_provider` from config once at startup.
- [ ] Skip `launchLlama()` and its watchdog in `lmstudio` mode; keep embedded behavior unchanged.
- [ ] Run JS syntax and launcher tests.

### Task 7: Final verification and live smoke
**Files:** No production changes unless a failing acceptance test identifies a defect.
- [ ] Run architecture and verification invariant checks.
- [ ] Run targeted Dorch/XToys/ControlQueue/autonomous/chat/UI tests.
- [ ] Run the full pytest suite to completion.
- [ ] Run `python -m uni.webui.verify_vision` against the user's live LM Studio.
- [ ] Connect to live Intiface with no device and verify status is connected/server-up with empty devices and positive motion is rejected truthfully.
- [ ] Record final Git diff/status and summarize remaining non-blocking legacy debt.