# Hermes runtime review — coordinator verdict

Date: 2026-07-31

Scope: canonical package `uni/`.

## Confirmed critical defects

1. `uni/capabilities/xtoys.py` reports success after its fallback click path
   without proving the requested XToys state changed. The fallback also has no
   local exception-to-result conversion.
2. `uni/capabilities/vision.py` passes the complete VLM response directly to
   `json.loads`, so fenced JSON or leading prose is rejected.
3. Vision detects coordinates on a resized screenshot but does not transform
   them back to original-screen coordinates before they can reach desktop
   input.
4. `Agent.get_state()` reads a second state field which is never synchronized
   with `EventLoop.state`.

## Confirmed, but not immediate hotfix scope

- All static tool schemas are sent to the model regardless of registered or
  enabled capabilities.
- `SPEAKING` is not used by the current event loop.
- `computer.type_text` uses `pyautogui.typewrite`, which is not a reliable
  Unicode text-entry mechanism.
- `ToolRegistry` is unused by the current event loop.
- A nested `uni/uni` source copy exists.
- Bare `except:` clauses exist in `brain.py`, `vision.py`, and `xtoys.py`.
- Conversation history is rebuilt for every cycle.

These items intersect the accepted runtime-contract, router, and event-loop
migrations. They must be handled by separate bounded tasks rather than a broad
legacy-code rewrite.

## Needs runtime evidence

The Piper return type and sample-rate concern is plausible, but the coordinator
environment does not currently have `piper-tts` installed and the dependency is
only lower-bounded (`piper-tts>=1.2`). Hermes must record the installed version,
inspect the actual return value, and provide a non-audio-device unit test before
any TTS patch is accepted.

The value `api_key="lm-studio"` is a dummy credential commonly required by an
OpenAI-compatible local endpoint. It is a portability/configuration issue, not
a leaked-secret or critical security defect.

## Decision

Hermes is authorized for the two approved hotfix tasks in
`.uni-dev/tasks.yaml`. Broad cleanup, contract changes, and capability-router
redesign are not authorized under those tasks.
