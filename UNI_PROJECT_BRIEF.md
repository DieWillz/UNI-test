# UNI — Project Brief (for external reviewers)

> Self-contained. Read this alone; no other file required. No keys, tokens, config contents, or personal data — only paths, facts, numbers.
> Snapshot: 2026-08-13. Canonical code: `C:\LLM\UNI\uni`. Runtime: Python 3.12.0, Windows 10/11 x64.

---

## 1. Mission & essence

UNI is a **local-first Windows AI operator**. It is not a single chatbot — it is a **swarm of roles** (personas/agents) coordinated by a **human coordinator** (the user). The coordinator defines intent; UNI executes locally: talks, controls the browser/computer, sees the screen, hears via microphone, speaks via TTS, remembers, runs autonomous loops, and optionally drives XToys/Intiface devices.

Three interfaces:
- **CLI** (`python -m uni`) — text/voice interactive agent.
- **WebUI / Admin** (`python -m uni.webui`) — local HTTP server on `127.0.0.1:8787`.
- **Electron Desktop Companion** (`uni/desktop`) — transparent overlay window, 383×640, bottom-right, with avatar (SVG/VRM), chat, buttons, STOP, and a tray "Показать" (Show) item.

The LLM brain is an **OpenAI-compatible endpoint** — today LM Studio at `127.0.0.1:1234` (`GET /v1/models` → 200). The product goal is to make this work on **any Windows PC** with a one-click installer and a built-in runtime (no manual LM Studio install).

---

## 2. Architecture as-is

```
C:\LLM\UNI\
├─ uni\                     # CANONICAL production code (only this tree is authoritative)
│  ├─ __main__.py           # CLI entrypoint  (python -m uni)
│  ├─ agent.py              # Agent: assembles Brain, capabilities, memory, EventLoop
│  ├─ brain.py              # LLM client (OpenAI-compatible)
│  ├─ config.py             # Pydantic config loader (config.yaml)
│  ├─ contracts.py          # Action / ActionResult / Observation models
│  ├─ capabilities\         # speech, computer, camera, browser, vision, memory, xtoys
│  │   ├─ base.py           # capability base contract (the ONLY allowed import target)
│  │   ├─ speech.py         # TTS (Piper/Silero) + STT wiring (sounddevice lazy-loaded)
│  │   ├─ stt.py            # speech-to-text (faster-whisper, lazy model load)
│  │   └─ camera.py / vision* / computer* / browser* / memory* / xtoys*
│  ├─ council\              # parallel external/local advisors (untrusted data)
│  ├─ devcoord\             # dev coordination: verify + apply changes
│  ├─ desktop\              # Electron overlay (main.js, preload.js, renderer/)
│  │   ├─ main.js           # single BrowserWindow 383×640, tray, STOP, capture
│  │   ├─ preload.js        # bridge (exposeInMainWorld 'uni')
│  │   └─ renderer\         # index.html, app.js, avatar.js, style.css, assets/
│  ├─ webui\                # HTTP server (admin + chat + vision + roles + ...), port 8787
│  │   └─ server.py         # ThreadingHTTPServer, ~2600 lines, all /api/* routes
│  ├─ roles\                # role definitions (loader uses absolute roles dir)
│  ├─ assets\voices\        # bundled Piper voice (ru_RU-irina-medium.onnx + .json)
│  └─ check_architecture.py # ADR-0005 audit (py -3.12 -m uni.check_architecture --strict)
├─ tests\                   # canonical pytest suite (264 tests, all passing)
├─ config.yaml              # local runtime config (validated by Pydantic)
├─ downloads\               # heavy assets: llama.cpp binaries, Piper voice
├─ agents\                  # AI working dirs + exchange
│  ├─ uni-codex\outbox\      # >>> exchange folder for Codex / external reviewers <<<
│  └─ artifacts\            # large logs / screenshots
└─ UNI_*.md                # UNI_STATUS / UNI_TASKS / UNI_CONTEXT / UNI_PROJECT_BRIEF
```

**Dispatch invariant (ADR-0005):** `EventLoop → CapabilityRouter → Capability`. A concrete capability MUST NOT import another capability, nor the router/planner/event_loop/agent. Enforced by `uni.check_architecture`.

**Ports observed (2026-08-13):** `8787` WebUI/admin, `1234` LM Studio (LLM). Optional/legacy: `7860` Vision Gradio (unused), `9222` Browser CDP, `1240` Codex-compatible — none required for the core path.

**Launch methods (verified working):**
- `cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m uni`
- `… -m uni.webui` → `http://127.0.0.1:8787/`
- `uni\desktop\start.bat` (Electron)

> WebUI port comes from `config.yaml`; the CLI `--port` flag is ignored (documented behavior).

---

## 3. Current state (2026-08-13, with proof)

| Area | Status | Evidence |
|---|---|---|
| Canonical code `uni/` | WORKS | pytest 264 passed / 0 failed (64.6 s, py3.12) |
| Python 3.12.0 | WORKS | `--version` = 3.12.0 |
| LLM endpoint 1234 | WORKS | `GET /v1/models` → 200 |
| WebUI/admin 8787 | WORKS | real curl: `/api/heartbeats` 200 (Hermes present), `/api/roles` 200 (3 roles) |
| Vision capture contract | WORKS | `POST /api/vision/capture` + `image_b64` → 200 `source:desktop` valid PNG data URL (0.002 s); no body + no camera → 409 fast |
| STT `/api/stt` | WORKS | JSON probe → 400 in 0.002 s (no model load); real audio path lazy-loads Whisper |
| TTS Piper/Silero | WORKS | `test_local_piper_voice_produces_native_rate_audio` PASS (real 22050 Hz audio) |
| Desktop (code) | WORKS (code) | `node --check` 4 JS files OK; width 383×640; avatar/STOP/tray present. Live window E2E **NOT done** (no display in this session) |
| Roles | WORKS | `/api/roles` → 3 roles; loader uses absolute dir |
| Architecture audit | WORKS | `uni.check_architecture --strict` → 0 errors, 0 warnings |
| Camera / real device | NOT VERIFIED | unit tests ≠ real camera; correct 409 on missing camera |
| Council / Autonomous / XToys device | NOT VERIFIED | depend on keys/hardware not present here |
| Windows installer `.exe` | NOT DONE | goal of packaging track |

**Recent fixes (Hermes, 2026-08-13):** 6 test failures → 0. Two were erroneous tests (case `'hermes'` vs `'Hermes'`, now resolved against the live registry); two were broken mock patch-points (`sd` module-global, now patched correctly, real logic still exercised); one was a production defect (`/api/stt` loaded a 140 MB Whisper model on a JSON probe → ~7 s timeout, now rejected before model load); one was a missing external asset (Piper voice downloaded 63 MB + cwd-independent path resolution added).

A pre-existing stale report (`PYTEST_VISUAL.xml`, 13 failures) is outdated — the real baseline after environment correction is **264 passed / 0 failed**.

---

## 4. Packaging goal

Ship UNI to **any Windows 10/11 x64 PC** as a one-click install, with a **built-in runtime** so the user does not manually install LM Studio, torch, etc.

Target components:
- **One-click installer** (`UNI-Setup.exe`) + optional **portable/offline** package.
- **Built-in LLM runtime**: bundle **llama.cpp** (binaries already downloaded to `downloads/` — `llama-b10375-bin-win-{cpu,cuda-12.4,rocm-7.14}-x64.zip`) instead of requiring LM Studio. Expose the same OpenAI-compatible port.
- **torch-free TTS/STT/VLM**: Piper (already bundled) for TTS; faster-whisper (CPU) for STT; a lightweight VLM for vision — all CPU-capable, with honest CPU fallback.
- **Launcher with watchdog**: `UNI-Launcher.exe` starts the server, monitors health, restarts on crash, supports **dev** (verbose) and **user** (silent) modes.
- **Clean-VM acceptance test**: a scripted run in a fresh Windows VM proving first-boot works without manual steps.

CPU is the mandatory base profile; GPU (CUDA/ROCm) is a validated acceleration with a truthful CPU fallback.

---

## 5. Invariants for proposers (do NOT violate)

1. **Nothing deleted physically.** To remove/replace a fragment, mark it `DEPRECATED by Hermes` with reason+date as a comment, or move it to a sibling `*.deprecated` file. This rule overrides almost everything else.
2. **`capability` does not import `capability`** (ADR-0005). Infrastructure (base contract, registry, config, contracts) is allowed. `uni.check_architecture` enforces this.
3. **local-first.** Assets resolve from local paths (`downloads/`, `uni/assets/voices/`, cwd) without network by default.
4. **mock ≠ E2E.** A passing unit test with a fake is not proof a feature works. "WORKS" requires fresh observed evidence (ACTION→RESULT→OBSERVATION: PID/port, real HTTP status, decoded artifact).
5. **"WORKS" only with fresh observable proof.** Stale screenshots/fallbacks do not count.
6. **Config/secret hygiene.** No keys/tokens in shipped docs, bundles, or logs. Secrets → local secret store / environment.

---

## 6. Questions for the reviewer

We ask an external AI (no prior project context) to propose improvements, especially packaging:

- **What is broken or risky** in the current `uni/` structure for a clean Windows package? (e.g. the duplicate `agents/uni*` trees, `uni/webui/desktop` vs `uni/desktop` legacy split, copy files `style — копия.css` / `app — копия.js`.)
- **How to package most reliably?** Concrete tech: NSIS vs Inno Setup vs MSIX; how to bundle llama.cpp + python runtime (embedded Python? pyinstaller?); offline vs online installer; signing.
- **Runtime isolation:** embed Python 3.12 + venv inside the install, or ship a portable Python? How to avoid the broken-`pydantic_core` venv trap we hit (Hermes desktop app venv leaked into `PYTHONPATH`).
- **VLM choice** for vision that is torch-free / CPU-friendly and gives a real current-screen PNG (not a stale file).
- **Watchdog/launcher** design: what restart/health-check strategy is robust on Windows (no job-control shell quirks)?
- **Clean-VM acceptance:** what minimal automated checks prove first-boot success without a display (headless HTTP + file artifacts)?
- **Single source of truth** for dependencies: `root requirements.txt` vs `uni/requirements.txt` vs `pyproject.toml` currently diverge — propose one lock/constraints file.
- **Git/versioning:** `C:\LLM\UNI` is not a git repo — recommend init + branch strategy for safe external contributions.

---

## 7. Appendix — artifact paths & commands

- Tests: `cd C:\LLM\UNI && PYTHONPATH=C:\LLM\UNI C:\LLM\python312\python.exe -m pytest -p no:cacheprovider -o asyncio_mode=auto`
  - Result 2026-08-13: **264 passed, 0 failed, 7 subtests passed** (64.59 s).
  - JUnit: `agents/uni-codex/outbox/HERMES_PYTEST.xml`.
- Audit: `C:\LLM\python312\python.exe -m uni.check_architecture --strict` → `0 errors, 0 warnings`.
- JS syntax: `node --check` on `uni/desktop/main.js`, `preload.js`, `renderer/app.js`, `renderer/avatar.js` (exclude `node_modules`) → 0 failures.
- Exchange folder for external reviewers / Codex: `C:\LLM\UNI\agents\uni-codex\outbox\`
  - `HERMES_PYTEST.xml`, `REPORT_HERMES_FINAL.md`, `CAPTURE.png`, `CODEX_SHOT_1.png` (regenerated in this effort; some E2E artifacts still pending live window run).
- Voice asset: `downloads/ru_RU-irina-medium.onnx` (+`.json`), mirrored in `uni/assets/voices/`.
- llama.cpp binaries (for packaging): `downloads/llama-b10375-bin-win-*.zip`.
- Status/tasks/context: `UNI_STATUS.md`, `UNI_TASKS.md`, `UNI_CONTEXT.md` (all in repo root).
