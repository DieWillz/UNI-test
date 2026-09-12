# UNI Hermes Continuous Work Implementation Plan

> **For agentic workers:** Execute task-by-task continuously. Do not stop after a task to ask for permission. If one task is blocked by a file another agent is actively editing, record the blocker, switch to the next independent task, and return later.

**Goal:** Bring the current UNI branch to a verified end-to-end state for Telegram, Operator, speech/media integration, and existing Dorch control without weakening the protected verification invariant.

**Architecture:** Keep Telegram as a transport boundary that normalizes messages into UNI models. Route privileged actions through the existing Operator/permission/verification layers. Keep media generators provider-neutral behind `uni/media/contracts.py`; transport only receives/sends files.

**Tech Stack:** Python 3.12, asyncio, pytest, existing UNI packages and standard-library networking unless an already-pinned dependency exists.

**Spec:** `AGENTS.md` plus the current UNI requirements. Dorch stabilization details remain in `docs/superpowers/specs/2026-09-04-dorch-stabilization-design.md`.

## Global Constraints

- Work only in canonical `C:\LLM\UNI`; do not create a parallel project copy.
- Shared working tree is dirty and multiple agents are active. NEVER run `git reset --hard`, `git clean`, broad `git checkout`, or whole-tree `git stash`.
- Before editing a file, run `git status --short -- <path>` and inspect its current diff. If it changed unexpectedly while you were working, stop touching that file and move to another task.
- Never delete/restore unrelated backups or untracked files just to make `git status` clean.
- Stage only explicit files. Before every commit run `git diff --cached --name-only`; if foreign files are staged, do not commit until staging is isolated safely.
- Preserve `COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED`. Tool return, HTTP 200, process existence, or model narration is not verification evidence.
- Do not weaken protected files in `.github/CODEOWNERS`. Run `C:\LLM\python312\python.exe scripts\check_verification_invariant.py` before claiming completion.
- Use focused tests after each task; run broader suites only at milestones.
- Never hardcode Telegram bot tokens, user secrets, chat IDs, or credentials in source/tests/logs.
- Continue automatically from one task to the next until all tasks are complete or there is a genuine external blocker.

## Verified baseline at plan creation

- `tests/test_verification_invariant.py`: 5 passed; invariant script PASS.
- Dorch/Xtoys/speech/screen-watch focused suite: 30 passed.
- `tests/operator + tests/transports`: 201 passed, 1 failed after pytest collection was fixed.
- Remaining failure: `tests/transports/telegram/test_retry.py::test_successful_send_after_retries`.
- `uni/transports/telegram/config.py` currently contains duplicate `__repr__` definitions.
- Retry settings exist in `TelegramConfig`, but the concrete sender currently calls API methods directly without a retry layer.

---

### Task 1: Stabilize shared test collection and baseline

**Files:** `pytest.ini`; do not rename existing test modules unless required.

- [ ] Confirm `pytest.ini` contains `pythonpath = . tests/operator` and `--import-mode=importlib` in `addopts`.
- [ ] Run `python -m pytest tests\operator tests\transports -q --disable-warnings --maxfail=5`.
- [ ] Expected baseline is exactly one retry-related failure, not collection errors.
- [ ] If the baseline differs because another agent changed code, diagnose the new failure before continuing.

### Task 2: Implement real bounded Telegram retry

**Files:** create `uni/transports/telegram/retry.py`; modify `uni/transports/telegram/adapter.py`; modify `tests/transports/telegram/test_retry.py`.

**Required behavior:** Retry only transient failures. Retry 429, 500, 502, 503, 504 and network/time-out style failures. Do not retry 400/401/403 or arbitrary permanent errors. Respect `max_retries`, `base_backoff_seconds`, and `respect_retry_after` from `TelegramConfig`.

- [ ] Rewrite the failing retry test so it calls the retry layer / concrete sender, not `_FakeTelegramApi.send_text()` directly.
- [ ] Add tests proving: 429 eventually succeeds; 401/403 are single-attempt; retry count is bounded; retry-after delay is honored; exhausted retry raises the final error.
- [ ] Implement one reusable async retry helper; do not duplicate retry loops for text/photo/document/voice/video.
- [ ] Wire `_ConcreteOutgoingSender` and `_ConcreteMediaSender` through that helper.
- [ ] Run `python -m pytest tests\transports\telegram\test_retry.py tests\transports\telegram\test_adapter.py -q`.
- [ ] Then rerun `python -m pytest tests\operator tests\transports -q --disable-warnings --maxfail=5` and require green.

### Task 3: Clean Telegram config and define runtime HTTP boundary

**Files:** `uni/transports/telegram/config.py`; create a focused Bot API client module only if one does not already exist.

- [ ] Remove the duplicate `TelegramConfig.__repr__` while preserving masked-token behavior.
- [ ] Add/keep tests proving token never appears in `repr`, exception text, or normal logs.
- [ ] Keep the adapter independent of a Telegram SDK. The concrete client must expose the methods the adapter already expects: `send_text`, `send_typing`, `send_photo`, `send_document`, `send_voice`, `send_video`.
- [ ] If no pinned async HTTP dependency exists, do not add a large framework merely for Telegram; prefer a minimal client compatible with the existing dependency policy.
- [ ] Return structured errors that expose status code and optional retry-after metadata to Task 2's retry helper.
- [ ] Add fake-HTTP tests; no live token is required for CI.
- [ ] Run all `tests\transports\telegram` tests.

### Task 4: Complete Telegram inbound loop and UNI routing

**Files:** `uni/transports/telegram/adapter.py`, `uni/transports/models.py`, routing/wiring module chosen by existing project conventions, `tests/transports/telegram/*`.

- [ ] Add a real start/stop loop that receives Telegram updates, normalizes them to `InboundMessage`, and calls the registered UNI handler.
- [ ] Preserve dedup bounds and chat/topic-scoped conversation IDs.
- [ ] Prove bot messages cannot loop back into UNI.
- [ ] Prove group mention/reply policy and allowlist/public behavior match `permissions.py` and `sessions.py`.
- [ ] Do not allow transport code to execute Windows actions directly. Privileged requests must flow through UNI/Operator permission checks.
- [ ] Add an end-to-end fake update test: Telegram update -> normalized inbound -> UNI handler -> outbound -> fake Telegram send.
- [ ] Run the transport suite and relevant Operator permission/routing tests.

### Task 5: Voice messages — Telegram STT/TTS round-trip

**Files:** `uni/transports/telegram/adapter.py`, existing `uni/capabilities/speech.py`, focused transport/speech tests.

- [ ] Reuse the existing UNI speech capability; do not build a second STT/TTS stack inside Telegram.
- [ ] Incoming Telegram voice must become text through STT while retaining the voice attachment metadata.
- [ ] Owner/public permissions must be evaluated using Telegram numeric identity, never username.
- [ ] Outgoing voice mode must synthesize UNI text through the existing TTS provider and send the resulting file.
- [ ] Add fake STT/TTS tests including empty transcription, provider failure, and text fallback.
- [ ] Confirm existing `tests/fasttrack/test_speech_input.py` remains green.

### Task 6: Media generation integration without transport coupling

**Files:** `uni/media/contracts.py`; add provider adapter modules under `uni/media/` only for backends actually available; transport tests as needed.

- [ ] Fix dataclass metadata fields to use safe factories instead of mutable/nullable dictionary defaults where appropriate.
- [ ] Keep `MediaGenerator` provider-neutral; Telegram must only send generated file paths/results.
- [ ] Add a small orchestration service that accepts image/edit/video requests, calls the selected provider, validates that the output file exists, and returns a normalized result.
- [ ] Do not claim generated media succeeded merely because a provider returned; verify the output path is fresh and readable.
- [ ] Wire Telegram outbound attachments to generated media through UNI, not directly from Telegram commands to a provider.
- [ ] Use a fake generator in tests; live ComfyUI/API checks are optional environment checks, never unit-test requirements.

### Task 7: Operator end-to-end completion

**Files:** existing `uni/operator/*`, `tests/operator/*`; touch protected event-loop files only if unavoidable and preserve the invariant.

- [ ] Run the full Operator suite first and capture any failures independently of Telegram.
- [ ] Verify action registry -> planner -> executor -> observation -> verifier flow for Windows, browser, and file provider actions.
- [ ] Add at least one acceptance test where the action returns normally but the postcondition is absent; terminal status must remain `not_verified`.
- [ ] Add at least one acceptance test where a fresh observation proves the postcondition; only then may terminal status become verified/successful.
- [ ] Confirm Telegram/public sessions cannot request owner-only Operator scope.
- [ ] Ensure recovery does not repeat destructive/non-idempotent actions blindly.
- [ ] Run `python -m pytest tests\operator -q --disable-warnings` and the invariant suite.

### Task 8: Dorch/Xtoys regression gate, not rewrite

**Files:** change Dorch/Xtoys only if a regression is demonstrated by a failing test or reproducible E2E observation.

- [ ] Rerun `tests/test_dorch_speech_sync.py`, `test_dorch_status.py`, `test_dorch_ui_contract.py`, `test_dorch_voice_mode.py`, `tests/fasttrack/test_xtoys_dom.py` and speech input tests.
- [ ] Current baseline is green (30 focused tests); do not refactor this subsystem merely for style.
- [ ] Preserve the distinction between command transmission and independently verified physical outcome.
- [ ] When Intiface is available without a physical device, report transport/server reachability separately from physical-motion verification.

### Task 9: Milestone integration and launch readiness

**Files:** only files required by observed failures; add concise docs/status notes if useful.

- [ ] Run `python -m pytest tests\operator tests\transports -q --disable-warnings`.
- [ ] Run the 30-test Dorch/speech regression gate.
- [ ] Run `C:\LLM\python312\python.exe scripts\check_verification_invariant.py` and `python -m pytest tests\test_verification_invariant.py -q`.
- [ ] Run a broader project test pass. Classify failures as new regression, pre-existing unrelated failure, environment dependency, or flaky test; do not hide failures.
- [ ] Smoke-test UNI startup with the existing launch path. Verify readiness from fresh observations rather than process existence alone.
- [ ] If Telegram credentials are available only in environment/config, perform a minimal live smoke check without printing the token: get bot identity, receive one owner message, return one text reply, then test one voice/media path if configured.
- [ ] Record concrete evidence for what works and list any environment-only blockers.

## Continuous execution / commit protocol

After every independently green task:

1. Run `git status --short` and `git diff -- <files-you-touched>`.
2. Run `git diff --cached --name-only`. Never include another agent's staged files.
3. Stage only exact files from the completed task.
4. Commit with a narrow message such as `fix(telegram): add bounded retry` or `test(operator): cover verification postconditions`.
5. Immediately continue to the next unchecked task. Do not stop to ask the user whether to proceed.
6. If another agent is actively changing the same file, do not overwrite it. Note `BLOCKED-CONCURRENT:<path>`, work on the next independent task, then revisit it after other tasks.
7. If a task requires weakening permissions, verification, or safety invariants, do not do it; preserve behavior and choose a different implementation.
8. When all tasks are exhausted, rerun milestone tests and produce a factual report: files changed, commits, exact tests/results, live checks, and remaining blockers.

## Definition of done

The plan is complete only when Telegram text/voice/media paths are wired through UNI with permissions, retries are bounded and tested, Operator actions retain independent verification, Dorch regressions remain green, protected invariant checks pass, and any remaining failures are explicitly documented with reproducible evidence.
