# GPT UNI Browser Execution Recovery — Result Handoff

> AGENT: **MT_DeepSeek UNI agent** (registered lane; ACK revision `a9ad83b74a16819e703cecf019cab54c9969aba65b393dc27d8861e1ab8bfee3` -> renamed to `MT_DeepSeek UNI agent`, ACK `51f66451fb47c38afed97ca95903947f4a1a7f653877c6eba5b8485fb66ce8af`)
> DATE: 2026-09-12
> STATUS: **CODE_GREEN_LIVE_PARTIAL** — unit/integration GREEN + live browser E2E VERIFIED; live LLM planning not verifiable in this environment (LM Studio model returns empty text; see REMAINING).

---

## ROOT CAUSES

1. **Planner context overflow (P0 — the 9012-token request).**
   - `MissionPlanner._catalog_text()` serialized the **entire** `planner_catalog()`: 48 actions, each with full param schemas (`scope`, `snapshot_id`, `tab_id`, `scroll_budget` descriptions) = **13 644 chars** (~3 900–6 000 tokens under Cyrillic-heavy llama.cpp tokenization).
   - `_scene_text()` serialized up to 60 elements with full metadata and value, up to **16 000 chars**.
   - System prompt ~336–500 tokens of dense instructions.
   - Repair attempt (attempt=1) appended full previous assistant+user output, **doubling** the context.
   - Measured single call before fix: **~6 600 tokens** (conservative estimate); real llama.cpp tokenization of Cyrillic pushes this past **9 000** — matching the observed `9012 > n_ctx=5120`.

2. **CDP attach failure killed the task.**
   - `BrowserSession.start()` threw `RuntimeError("cdp_attach_failed_no_browser_launched")` whenever `connect_over_cdp` failed, even though a managed browser could still be launched. The error propagated through `PerceptionBroker.observe() -> browser_provider.inspect() -> DOMOperator.inspect()` as `dom_unavailable`, and then `MissionExecutor` turned it into `Stopped at 1: cdp_attach_failed_no_browser_launched`.
   - CDP is only one execution mechanism; a user's ordinary open browser must not fail the whole task.

3. **`click_cannot_fill_text_field` blocked valid plans.**
   - The planner validator rejected any `operator.desktop.click` whose postcondition was an element value change on a textbox. But the model had **no way** to express the correct multi-step `focus -> fill -> press` because the catalog was huge and unwieldy, and the check lived in `plan()` (not in the static `parse_plan_text` contract), so it fired inconsistently.
   - `operator.browser.current_tab` was absent from the scoped catalog while the model produced that spelling; `browser.current_tab` exists as the canonical alias.

4. **TTS failure broke the browser task.**
   - `event_loop._speak()` did not catch exceptions from `tool_executor.execute("speech.speak", ...)`. When Piper/Silero raised `RuntimeError("... не вернул аудио")`, the exception propagated through `_process_input` / `_run_background_input`, aborting the surrounding task (including a successful browser action).

---

## CHANGED

- `uni/operator/planner.py`
  - Added task-specific catalog selection: `_catalog_text(scope="browser"|"desktop"|None)`.
    - `scope=None` → legacy full catalog (backward compatible).
    - `scope="browser"` → **23 curated actions**, compact form (name + description + requires_target, **no param schemas**) = **~2 276 chars**.
    - `scope="desktop"` → small desktop/file set.
  - Added `_system_prompt(scope=...)`, `_user_prompt(...)`, `_context_budget(...)`, `_estimate_tokens()`, `_looks_like_browser_goal()`.
  - `plan()` now: chooses scope deterministically, logs `planner.context_budget` + `planner.context_compacted`, compacts by dropping failure context when over budget, **never** ships full catalog for a short command.
  - Moved the `click_cannot_fill_text_field` check into `parse_plan_text()` (static contract, with scene) so validator and planner share one code path.
  - Added deterministic alias normalization: `operator.browser.current_tab` → `browser.current_tab` (registered canonical read), so a legitimate plan is not wrongly rejected.
- `uni/browser_session.py`
  - `start()` now **falls back to a managed persistent-context launch** when `connect_over_cdp` fails, instead of throwing immediately. CDP attach failure is recorded, playwright instance is reused for launch. If both CDP and managed launch fail, the **real** launch reason surfaces (factual fail), no synthetic CDP-only code.
- `uni/event_loop.py`
  - `_speak()` wraps `speech.speak` in try/except: TTS failure is logged (`tts.unavailable`), returns `False`, and does **not** propagate into the surrounding browser task.
- `docs/handoffs/UNI_ACTIVE_WORK.md`
  - Registered lane `MT_DeepSeek UNI agent` (owner directive 2026-09-12), ACTIVE, with exclusive/read-only paths.
- `tests/operator/test_browser_execution_recovery.py` (new)
  - 8 RED→GREEN tests: catalog compactness, context budget, focus→fill→press validity, click-with-value still rejected, CDP fallback, real-failure surfacing, TTS isolation.

---

## PLANNER CONTEXT BEFORE

- total estimated tokens (single call): **~6 600** (heuristic) / **>9 000** real (matches observed `9012`)
- n_ctx: **5120**
- major contributors:
  1. full 48-action catalog with schemas: **13 644 chars**
  2. scene with 60 elements + metadata: up to **16 000 chars**
  3. dense system prompt: ~336–500 tokens
  4. repair round duplicating context

## PLANNER CONTEXT AFTER

- scope=browser, compact catalog: **23 actions / 2 276 chars**
- scene capped at 2 500 chars, metadata/value stripped
- total estimated tokens for the exact bug command: **~1 837** (est.)
- budget: **4 220** (n_ctx 5120 − reserved 900)
- compacted blocks: failure context dropped on over-budget; no raw DOM values/metadata in scene
- **Reduction: ~3.6× (token estimate); ~6× (chars)** — comfortably below n_ctx with ~2.3× headroom.

---

## BROWSER FALLBACK

- **CDP attach**: attempted first when `cdp_url` configured; on failure → managed launch fallback (no abort).
- **Managed launch**: persistent context with user profile; the fallback path.
- **UIA/keyboard/visible desktop**: untouched (existing `WindowsProvider`/`VisibleDesktopDriver` remain the deterministic policy for desktop mode); planner `desktop` scope keeps desktop actions; `mouse_only` mode already routes to desktop.
- **OCR/Vision**: existing `PerceptionBroker` fallback resolver remains for target resolution.
- **Verification**: existing `PostconditionVerifier` — fresh observation, never tool ACK.

---

## TESTED (exact commands + results)

- `pytest tests/operator/test_browser_execution_recovery.py -q` → **8 passed**
- `pytest tests/operator -q` → **188 passed, 3 skipped**
- Full suite `pytest -q` → **960 passed, 0 failed, 5 skipped, 7 subtests passed**
- `python scripts/check_verification_invariant.py` → **PASS**
- `python -m uni.check_architecture --strict` → **0 errors, 0 warnings**

## LIVE E2E

- **E2E A — real headless Chrome via BrowserSession** (command: new tab + navigate to coral.ru):
  - `tabs_before=1` → `change_tab('new_tab')` → `tabs_after=2`
  - `navigate('https://coral.ru')` → observed active URL `https://www.coral.ru/`
  - independent observation: `active_url_observed=https://www.coral.ru/` → `VERIFIED_URL_CONTAINS_CORAL=True`
- **E2E B — full OperatorRuntime pipeline, deterministic plan with real browser, postcondition `browser.url_equals` (strict):**
  - Outcome: `status=not_verified`, reason `browser_url_mismatch` (site redirected to `www.` — correct fail-closed behavior; toolbar-equal URL is a semantic mismatch)
- **E2E B2 — same pipeline, postcondition `browser.url_contains` (semantic, handles redirects):**
  - Outcome: `status=verified`, `verified=True`, `message='Mission completed and independently verified'`
  - evidence: `source=browser`, `observed=https://www.coral.ru/`, `expected=coral.ru`, snapshot fresh.

## TTS

- `_speak()` now isolates TTS exceptions: log `tts.unavailable`, return `False`, task continues. Unit test proves an exploding Piper executor no longer raises.

---

## REMAINING

1. **Live LLM planning not verifiable in this environment**: LM Studio endpoint `127.0.0.1:1234` (qwen3.5-9b) returns empty text for even a plain prompt (`error=None, text=''`). The planner's RED tests are structural; the live `plan()` call could not produce a model plan here. On a machine with a working local model, run the full user scenario end-to-end; the pipeline (context budget + validation + execution + verification) is proven by unit + live-browser E2E.
2. `n_ctx` increase (e.g. LM Studio 8k–16k) remains a recommended supplementary setting, not the primary fix; the architectural fix (compact context) is in place.
3. TTS root cause (`Piper не вернул аудио` for some providers) is **not** fixed here by design (scoped out). It is now isolated from the task flow; a dedicated speech lane should diagnose the provider.

---

## OWNERSHIP CONFLICTS

- None encountered for this lane's paths. All `direction_sync check` returned `ALLOW / CURRENT`.
- Lane `MT_DeepSeek UNI agent` registered with exclusive paths under `uni/operator/*`, `uni/event_loop.py`, `uni/browser_session.py`, new tests, and this handoff file. Read-only: `uni/devcoord/**`, `uni/transports/**`, `uni/webui/**`, `uni/agent.py`, `uni/autonomous*`, `uni/control_queue.py`, `uni/xtoys_control_coordinator.py` (owner-reserved) — untouched.

---

_RESULT: CODE_GREEN_LIVE_PARTIAL (unit/integration GREEN; live browser E2E VERIFIED; live LLM planning NOT VERIFIED due to model environment)._