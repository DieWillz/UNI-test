# UNI Project — Full Codebase Analysis

**Date:** 2026-08-13  
**Analyzed by:** opencode agent  
**Repository root:** `C:\LLM\UNI`  
**Canonical code:** `C:\LLM\UNI\uni\`  

---

## 1. Executive Summary

UNI is a **local-first Windows AI operator** — a swarm of roles (personas/agents) coordinated by a human. It provides three interfaces:
- **CLI** (`python -m uni`) — text/voice interactive agent
- **WebUI/Admin** (`python -m uni.webui`) — local HTTP server on `127.0.0.1:8787`
- **Electron Desktop Companion** — transparent overlay window (336×660), bottom-right above taskbar tray

The LLM brain uses an **OpenAI-compatible endpoint** — currently embedded llama.cpp at `127.0.0.1:1235` (launched by `scripts/launcher.js`).

**Current verified state (2026-08-13):**
- ✅ 264 pytest tests passing
- ✅ Architecture audit (`uni.check_architecture --strict`) → 0 errors, 0 warnings
- ✅ WebUI, Vision capture, STT, TTS, Desktop overlay all working with live evidence
- ✅ Launcher (`UNI.bat` → `node scripts/launcher.js`) brings up full stack
- ❌ Windows installer `.exe` — NOT DONE (packaging track goal)
- ❌ Real camera device — NOT VERIFIED
- ❌ Council/Autonomous/XToys device — depend on keys/hardware not present

---

## 2. Architecture Overview

### 2.1 Directory Structure (Canonical)

```
C:\LLM\UNI\
├─ uni\                     # CANONICAL production code (only this tree is authoritative)
│  ├─ __main__.py           # CLI entrypoint
│  ├─ agent.py              # Agent: assembles Brain, capabilities, memory, EventLoop
│  ├─ brain.py              # LLM client (OpenAI-compatible)
│  ├─ config.py             # Pydantic config loader (config.yaml)
│  ├─ contracts.py          # Action / ActionResult / Observation models (ADR-0004)
│  ├─ capabilities\         # speech, computer, camera, browser, vision, memory, xtoys
│  │   ├─ base.py           # Capability base contract (ONLY allowed import target)
│  │   ├─ speech.py         # TTS (Piper/Silero) + STT (faster-whisper)
│  │   └─ ...               # computer, camera, browser, vision, memory, xtoys
│  ├─ council\              # parallel external/local advisors (untrusted data)
│  ├─ devcoord\             # dev coordination: verify + apply changes
│  ├─ desktop\              # Electron overlay (main.js, preload.js, renderer/)
│  ├─ webui\                # HTTP server (admin + chat + vision + roles), port 8787
│  ├─ roles\                # role definitions (loader uses absolute roles dir)
│  ├─ assets\voices\        # bundled Piper voice
│  └─ check_architecture.py # ADR-0005 audit enforcement
├─ tests\                   # canonical pytest suite (264 tests)
├─ config.yaml              # local runtime config (validated by Pydantic)
├─ downloads\               # heavy assets: llama.cpp binaries, Piper voice
├─ agents\                  # AI working dirs + exchange (NOT canonical code)
├─ scripts\launcher.js      # Node launcher: llama:1235 + webui:8787 + electron
└─ UNI_*.md                 # status, tasks, context, project brief
```

### 2.2 Core Architecture Invariants (ADR-0005)

**Dispatch invariant:** `EventLoop → CapabilityRouter → Capability`  
- A concrete capability **MUST NOT** import another capability
- A capability **MUST NOT** import `router/planner/event_loop/agent`
- Enforced by `uni.check_architecture` (AST-based)

### 2.3 Data Flow

```
User/UI (CLI | WebUI | Electron)
       │
       ▼
  Agent / EventLoop (uni/agent.py + uni/event_loop.py)
       │
       ├─ Brain ──→ OpenAI-compatible endpoint (llama.cpp :1235)
       ├─ ToolExecutor ──→ CapabilityRegistry ──→ Capabilities
       ├─ WorkingMemory (persistent facts + dialogue)
       ├─ SessionLogger (append-only observable log)
       └─ AutonomousController (hands-free mode)
```

---

## 3. Key Components Analysis

### 3.1 CLI Entry Point (`uni/__main__.py`)
- Clean argparse setup with modes: `--text`, `--voice`, `--autonomous`, `--webui`, `--demo xtoys`
- Proper UTF-8 stream reconfigure
- Rich console for pretty output
- Graceful shutdown with `finally` block

### 3.2 Agent Assembly (`uni/agent.py`)
- **Single responsibility**: wires together all components
- Creates: Brain, BrowserSession, WorkingMemory, 7 Capabilities, ToolExecutor, EventLoop, AutonomousController
- Role loading with fallback to default
- Capability registration via `CapabilityRegistry` (no cross-imports)

### 3.3 Brain (`uni/brain.py`)
- OpenAI-compatible async client
- **Model resolution**: auto-detects loaded model from `/v1/models` endpoint
- Vision support with separate client config
- Healthcheck endpoint
- Proper error handling → `BrainResponse` with error field

### 3.4 Config (`uni/config.py`)
- **Pydantic v2** models for all configuration sections
- **Provider switching**: `llm_provider: "embedded"` (llama.cpp :1235) vs `"lmstudio"` (DEPRECATED :1234)
- `effective_base_url` property handles provider switching transparently
- Comprehensive configs: Brain, Browser, Computer, Camera, Speech, Vision, XToys, Agent, Logging, Autonomous, Council, Memory, Demo

### 3.5 EventLoop (`uni/event_loop.py`) — **~950 lines**
Central orchestration logic:
- **Direct command parsing** (regex-based) for XToys, camera, browser, vision, screen watch
- **Visual command routing** (`открой X`, `кликни X` → `VisualActionAgent`)
- **Free-form LLM chat** with tool calling
- **Autonomous override** for hands-free mode (stop/manual intensity priority)
- Camera watch with periodic reminders
- Screen watch (event-driven, VLM only on change)
- Web exploration loop
- Speech synthesis + playback with ESC interrupt

### 3.6 Contracts (`uni/contracts.py`) — ADR-0004
Canonical runtime contracts:
- `Action` — capability.action name + params + id
- `ActionResult` — success, message, data, error, **verified**, retry_count, timestamp
- `Observation` — source, summary, data, confidence, timestamp (bounded snapshots)
- `AgentContext` — serializable goal state passed through event loop
- Legacy `ToolResult` kept for backward compat with conversion methods

### 3.7 Capabilities (All follow `Capability` base contract)

| Capability | Key Features |
|------------|--------------|
| **speech** | Piper (offline) + Silero TTS; faster-whisper STT; lazy model loading; voice activation; sentence-by-sentence synthesis; audio file export |
| **vision** | Gradio (Moondream) or OpenAI-compatible VLM; desktop + browser capture; element location with confidence threshold (0.55); local UIA fallback opt-in |
| **computer** | pyautogui + win32/UIA; human-like mouse (Bezier curves, variable speed); accessibility element find/focus/read/write; app launch with lock; blacklist dangerous commands |
| **browser** | Playwright persistent context; search web/images; DOM click/type; screenshot; CDP attach support; agent cursor overlay |
| **camera** | OpenCV/dshow; brightness check; periodic snapshots with Vision analysis; spoken announcements |
| **memory** | Persistent JSON (facts + dialogue); secret redaction; hallucination marker filtering; bounded context retrieval |
| **xtoys** | Web automation via browser session; intensity/pattern control; remote session with TTL; motion-to-toy (optical flow) |

### 3.8 WebUI Server (`uni/webui/server.py`) — **~2600 lines, monolithic**
- `ThreadingHTTPServer` (stdlib only)
- **All `/api/*` routes in one file**: chat, council, TTS, STT, camera, vision, desktop, computer, autonomous, XToys, admin
- SSE endpoint for council rounds
- Secret masking (defense-in-depth)
- Launcher status/logs endpoints
- Self-test, demo mouse, overlay capture endpoints
- **Issues**: too large, mixes sync/async via `asyncio.run_coroutine_threadsafe`, hardcoded paths

### 3.9 Desktop Companion (`uni/desktop/`)
- **Electron** with `main.js` (445 lines), `preload.js`, `renderer/app.js` (691 lines, v4 universal UI engine)
- Transparent overlay, frameless, always-on-top, skip taskbar
- **Position**: 336×660, bottom-right **above taskbar** (workArea-based, DIP-aware)
- Tray: "Показать", "Скрыть", "Наблюдение: off/observe/suggest/act", "Диагностика", "Стоп", **"Выход" (kills full stack)**
- PNG avatar states (idle/listening/working/done/waiting)
- VRM avatar support (three-vrm) with offscreen capture to PNG states
- SSE via fetch (no http.get Parse Error)
- PTT microphone → STT
- Settings persist via preload bridge to `state.json`

### 3.10 Launcher (`scripts/launcher.js`) — **311 lines**
- **Single entry point**: `UNI.bat` → `node scripts/launcher.js`
- Spawns: llama-server (:1235), webui (:8787), electron, optional TTS (:7778)
- **Dedup by PORT** (not just PID) — detects orphaned instances
- `runtime/pids.json` for tracking
- **Electron flake handling**: up to 3 retries within 10s before killing stack
- Minimal HTTP `:8790` for: overlay status, screenshot, selftest, demo mouse, **`/api/launcher/stop` (kills full stack)**
- Graceful shutdown: electron → webui → llama → tts order

### 3.11 Autonomous Mode (`uni/autonomous.py`) — **386 lines**
- Three concurrent loops sharing `SessionState`:
  1. **VisionObserver** — periodic screenshot → VLM → screen_desc
  2. **SpeechDirector** — role-driven phrases via TTS (cancels prior)
  3. **DeviceController** — ramps/verifies XToys intensity
- Rare **Conductor** LLM step steers behavior
- Safety: device motion bounded by `max_intensity`, dual opt-in (`autonomous.enabled` + `xtoys.autonomous_physical`)
- Emergency stop: ESC/stop-word → intensity 0 immediately

### 3.12 Dev Coordination (`uni/devcoord/`)
- **Pipeline**: Counselor → Verifier → Aggregator → Applier → Knowledge Base
- `DevelopmentCoordinator` selects providers by past success + cost
- `Verifier` checks claims
- `Aggregator` picks best response with past-success bonus
- `Applier` applies patches (review branch, tests, **NO commit**)
- `KnowledgeBase` stores responses for learning

### 3.13 Council (`uni/council/`)
- Parallel external/local advisors (untrusted data)
- Browser automation for free web tiers (MANIFESTO v2.6 §7)
- Fair-use conditions: separate profile, rate limits, no paid subscription automation
- Critic + Coordinator synthesis
- Artifacts persisted locally

---

## 4. Test Suite (`tests/`) — 264 Tests

| Category | Count | Notes |
|----------|-------|-------|
| Fasttrack | ~15 | Working memory, visual UI operator, vision, speech, executor, commands, camera, browser, brain model selection |
| Council | 3 | WebUI TTS, WebUI, council |
| Devcoord | 1 | Development coordinator |
| Regression | 2 | Smoke + integration (3 visual action scenarios) |
| Other | ~240 | Visual action, vision Russian, trajectory store, safety, R queue, remote public base, motion trajectory, local vision fallback, knowledge base, human mouse, feed injector, event loop visual route, display calibration, devcoord verifier/applier/pipeline, desktop proactive/P0, API desktop/admin v3, agent act on screen, camera base64, audit A03/A02 |

**All passing** (64.6s on Python 3.12).

---

## 5. Identified Issues & Risks

### 5.1 Codebase Hygiene (High Priority)

| Issue | Location | Impact |
|-------|----------|--------|
| **Duplicate/legacy directories** | `agents/uni*`, `UNI-reuse-candidates/`, `uni/webui/desktop/` vs `uni/desktop/` | Confusion, risk of running wrong code, bloat |
| **Copy files** | `uni/webui/js/app — копия.js`, `uni/webui/css/style — копия.css` | Dead code, confusion |
| **Monolithic webui/server.py** | 2600+ lines | Hard to maintain, test, review; mixes concerns |
| **Mixed sync/async in HTTP handlers** | `uni/webui/server.py` uses `asyncio.run_coroutine_threadsafe` + `asyncio.run` fallback | Event loop leakage risk, hard to debug |
| **Hardcoded paths** | Multiple files reference `C:\LLM\UNI` explicitly | Breaks portability, packaging |

### 5.2 Architecture & Design

| Issue | Location | Impact |
|-------|----------|--------|
| **No unified dependency lock** | `requirements.txt` only at root; no `pyproject.toml` / `uv.lock` / `poetry.lock` | Reproducibility risk, version conflicts |
| **EventLoop too large** | 950 lines, handles everything | Violates SRP, hard to test in isolation |
| **WebUI routes all in one file** | 2600 lines | Same as above |
| **Capability `execute` returns legacy `ToolResult`** | All capabilities | Migration to `ActionResult` incomplete |
| **No health check aggregation** | Scattered across components | Hard to monitor system health programmatically |

### 5.3 Packaging & Distribution (Critical for Goal)

| Issue | Current State | Required |
|-------|---------------|----------|
| **Windows installer** | ❌ Not done | NSIS/Inno Setup + PyInstaller |
| **Embedded Python runtime** | ❌ Uses `C:\LLM\python312\python.exe` | Embed Python 3.12 + venv in installer |
| **CPU-first VLM** | ❌ Gradio (Moondream) requires torch | Moondream.cpp / LLaVA-CPP / SmolVLM-ONNX |
| **Torch-free STT/TTS** | ⚠️ faster-whisper + piper-tts work on CPU but need torch for Silero | Piper-only TTS; faster-whisper CPU confirmed |
| **Watchdog/launcher as .exe** | ⚠️ Node.js script | Compile to `UNI-Launcher.exe` (pkg/nexe) |
| **Clean VM acceptance test** | ❌ Not automated | Scripted headless HTTP + file artifact checks |

### 5.4 Security & Secrets

| Issue | Location | Mitigation |
|-------|----------|------------|
| **Secret redaction** | `WorkingMemory`, `SessionLogger` — regex-based | Good, but not exhaustive |
| **API keys in config.yaml** | Council config has empty `api_key` fields | Must use env vars / secret store |
| **No secret scanning in CI** | Not configured | Add trufflehog/gitleaks |

### 5.5 Testing Gaps

| Gap | Evidence |
|-----|----------|
| **Real camera E2E** | Unit tests mock; correct 409 on missing camera only |
| **Council browser automation** | Requires live browser + accounts; not in CI |
| **XToys device** | Requires hardware; not verified |
| **Autonomous mode E2E** | Depends on above |
| **Packaging verification** | No clean VM test |

---

## 6. Recommendations by Priority

### 🔴 P0 — Blockers for Packaging / Production

1. **Create `pyproject.toml` with locked dependencies**
   - Single source of truth for deps (replace `requirements.txt`)
   - Use `uv` or `poetry` for lock file
   - Separate `dev`, `cpu`, `cuda`, `rocm` extras

2. **Refactor `uni/webui/server.py` into modules**
   ```
   uni/webui/
   ├─ __main__.py
   ├─ server.py          # thin: routes → handlers
   ├─ handlers/
   │   ├─ chat.py
   │   ├─ council.py
   │   ├─ tts_stt.py
   │   ├─ vision_camera.py
   │   ├─ desktop.py
   │   ├─ computer.py
   │   ├─ autonomous.py
   │   ├─ xtoys.py
   │   └─ admin.py
   ├─ middleware.py      # auth, secret masking, CORS
   └─ sse.py             # Server-Sent Events helper
   ```

3. **Embed Python runtime for installer**
   - Use `pyinstaller` with `--runtime-hook` for venv activation
   - Or use `python-embed` (official Windows embeddable package) + `pip install --target`
   - Avoid system Python dependency entirely

4. **Choose CPU-first VLM**
   - **Recommended**: `moondream.cpp` (GGUF, ~1.7GB, runs on CPU via llama.cpp)
   - Alternative: `SmolVLM-ONNX` (ONNX Runtime, ~500MB)
   - Integrate via existing `vision` capability provider abstraction

5. **Build `UNI-Launcher.exe` from `scripts/launcher.js`**
   - Use `pkg` or `nexe` to compile Node.js launcher to single executable
   - Include `cloudflared.exe` for public tunnel
   - Watchdog: health checks every 30s, restart on crash, log rotation

6. **Clean VM acceptance test (headless)**
   ```powershell
   # Fresh Windows VM
   # 1. Run UNI-Setup.exe /SILENT
   # 2. Start UNI-Launcher.exe --headless
   # 3. Poll http://127.0.0.1:8787/api/uni/status → llama.running + webui.running
   # 4. POST /api/chat → verify reply
   # 5. POST /api/vision/capture (base64 PNG) → verify response
   # 6. POST /api/launcher/stop → verify all PIDs gone
   # 7. Check no residual processes/files
   ```

### 🟠 P1 — Architecture Improvements

7. **Complete `ActionResult` migration**
   - Update all capabilities to return `ActionResult` (with `verified`, `retry_count`)
   - Update `ToolExecutor` and `EventLoop` to use canonical contracts
   - Deprecate `ToolResult` with clear timeline

8. **Split `EventLoop` into focused classes**
   ```
   uni/
   ├─ event_loop.py           # core loop only
   ├─ command_router.py       # parse_direct_command + routing
   ├─ visual_router.py        # _try_visual_command + VisualActionAgent bridge
   ├─ autonomous_bridge.py    # _maybe_autonomous_override
   ├─ camera_watch.py         # _camera_watch_worker
   ├─ screen_watch.py         # _watch_screen_loop
   └─ exploration.py          # _explore_web
   ```

9. **Unify desktop implementations**
   - Remove `uni/webui/desktop/` (legacy)
   - Keep only `uni/desktop/` (canonical)
   - Update launcher to reference single path

10. **Configuration hygiene**
    - Single `config.yaml` schema documented
    - Environment variable overrides for all secrets
    - Validate config on startup with clear errors

### 🟡 P2 — Developer Experience

11. **Remove dead/duplicate files**
    - `agents/uni*` → archive or delete (NOT canonical)
    - `UNI-reuse-candidates/` → move to separate repo or delete
    - `uni/webui/js/app — копия.js`, `uni/webui/css/style — копия.css` → delete
    - `scripts/start_llm.bat.deprecated` → delete

12. **Add pre-commit hooks**
    - `ruff` / `black` / `isort` for Python
    - `eslint` / `prettier` for JS
    - `uni.check_architecture --strict` in CI

13. **Improve logging/observability**
    - Structured JSON logs (optional)
    - OpenTelemetry traces for EventLoop
    - Health endpoint aggregating all component statuses

14. **Document public APIs**
    - WebUI `/api/*` contracts (OpenAPI/Swagger)
    - Electron preload bridge (`window.uni`)
    - Launcher HTTP `:8790` endpoints

### 🟢 P3 — Nice to Have

15. **GPU acceleration profiles**
    - CUDA / ROCm / CPU auto-detect in launcher
    - Truthful fallback (no silent GPU→CPU degradation)

16. **Plugin system for capabilities**
    - Entry-point based discovery
    - Third-party capabilities without core modification

17. **Internationalization**
    - Extract Russian strings to message catalogs
    - Support en/ru UI toggle

---

## 7. File Inventory for External AI Review

These files provide a complete picture of the project:

| File | Purpose |
|------|---------|
| `UNI_PROJECT_BRIEF.md` | **Start here** — self-contained project brief for reviewers |
| `UNI_CONTEXT.md` | Canonical directories, architecture, entrypoints, rules |
| `ROADMAP.md` | Consolidation roadmap (Phases 0-5) |
| `docs/UNI_MANIFESTO_v2.6.md` | Mission, rules, architecture, signatures |
| `uni/__main__.py` | CLI entrypoint |
| `uni/agent.py` | Agent assembly |
| `uni/brain.py` | LLM client |
| `uni/config.py` | Pydantic config (all settings) |
| `uni/event_loop.py` | Main interaction loop |
| `uni/contracts.py` | Canonical contracts (ADR-0004) |
| `uni/check_architecture.py` | Architecture audit (ADR-0005) |
| `uni/capabilities/base.py` | Capability base contract |
| `uni/capabilities/registry.py` | Capability registry |
| `uni/capabilities/speech.py` | TTS/STT capability |
| `uni/capabilities/vision.py` | Vision capability |
| `uni/capabilities/computer.py` | Computer control capability |
| `uni/capabilities/browser.py` | Browser capability |
| `uni/webui/server.py` | WebUI HTTP server (monolithic) |
| `uni/desktop/main.js` | Electron main process |
| `uni/desktop/renderer/app.js` | Desktop UI (v4 universal engine) |
| `scripts/launcher.js` | Node.js launcher (full stack) |
| `requirements.txt` | Python dependencies |
| `tests/test_regression_integration.py` | Integration test examples |

---

## 8. Quick Start for New AI Reviewer

```bash
# 1. Read the brief
cat UNI_PROJECT_BRIEF.md

# 2. Understand context
cat UNI_CONTEXT.md

# 3. Check current status
cat UNI_STATUS.md

# 4. Run tests (verified baseline)
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -m pytest -p no:cacheprovider -o asyncio_mode=auto

# 5. Architecture audit
C:\LLM\python312\python.exe -m uni.check_architecture --strict

# 6. Launch full stack (one-click)
UNI.bat
# → WebUI: http://127.0.0.1:8787
# → Electron overlay appears bottom-right
```

---

## 9. Conclusion

**UNI is a working, well-tested local AI operator** with solid architecture foundations (ADR-0004/0005, capability isolation, contracts). The codebase is **production-ready for development use** but **not yet packaged for distribution**.

**Critical path to `UNI-Setup.exe`:**
1. Dependency lock (`pyproject.toml` + `uv.lock`)
2. WebUI modularization
3. CPU-first VLM integration (moondream.cpp)
4. Python embedding strategy (pyinstaller + embeddable Python)
5. Launcher → `UNI-Launcher.exe` (pkg/nexe)
6. NSIS/Inno Setup installer with clean VM acceptance test

The architecture supports all required features; the remaining work is **packaging engineering**, not core redesign.