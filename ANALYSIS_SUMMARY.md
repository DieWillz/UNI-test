# UNI Project Analysis — Quick Reference for External AI

**Generated:** 2026-08-13  
**For:** External AI reviewers / Codex / other agents  
**Purpose:** Minimal context to understand the project instantly

---

## 🎯 What is UNI?

**Local-first Windows AI operator** — not a chatbot, but a **swarm of roles** coordinated by a human.
- **Interfaces:** CLI, WebUI (localhost:8787), Electron Desktop overlay (336×660, bottom-right above tray)
- **Brain:** OpenAI-compatible endpoint → embedded llama.cpp (port 1235)
- **Capabilities:** Speech (TTS/STT), Computer control, Camera, Browser, Vision, Memory, XToys/Intiface
- **Modes:** Interactive, Autonomous (hands-free), Council (parallel AI advisors)

---

## 📁 Canonical Code Only

```
C:\LLM\UNI\uni\          ← ONLY this directory is production code
C:\LLM\UNI\tests\        ← Canonical tests (264 passing)
C:\LLM\UNI\config.yaml   ← Runtime config (Pydantic validated)
C:\LLM\UNI\downloads\    ← Heavy assets (llama.cpp, models, voices)
C:\LLM\UNI\scripts\      ← launcher.js (Node.js)
```

**IGNORE THESE (not canonical):**
- `agents/uni*` — AI working dirs, exchange folders
- `UNI-reuse-candidates/` — Old/experimental code
- `uni/webui/desktop/` — Legacy desktop (use `uni/desktop/`)
- Files with ` — копия` — Dead copies

---

## 🏗️ Architecture Invariants (MUST NOT VIOLATE)

| Rule | Enforcement |
|------|-------------|
| **Capability ≠ imports Capability** | `uni.check_architecture --strict` (AST) |
| **Capability ≠ imports router/planner/event_loop/agent** | Same audit |
| **Single canonical entrypoint** | `uni/__main__.py` |
| **ActionResult contracts** | `uni/contracts.py` (ADR-0004) |
| **Nothing physically deleted** | Mark `DEPRECATED by Hermes` + date |

---

## 🚀 Verified Working (2026-08-13)

```bash
# Tests
cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m pytest -p no:cacheprovider -o asyncio_mode=auto
# → 264 passed, 0 failed (64.6s)

# Architecture audit
C:\LLM\python312\python.exe -m uni.check_architecture --strict
# → 0 errors, 0 warnings

# One-click launch
UNI.bat
# → llama:1235 + webui:8787 + electron overlay
# WebUI: http://127.0.0.1:8787/
# Stop: tray "Выход" or POST :8790/api/launcher/stop
```

---

## 🔑 Key Files to Read (Priority Order)

| File | Why |
|------|-----|
| `UNI_PROJECT_BRIEF.md` | **Start here** — self-contained brief for reviewers |
| `UNI_CONTEXT.md` | Canonical dirs, architecture, entrypoints, rules |
| `uni/__main__.py` | CLI entrypoint |
| `uni/agent.py` | Agent assembly (Brain, capabilities, EventLoop) |
| `uni/brain.py` | LLM client (model resolution, vision) |
| `uni/config.py` | All settings (Pydantic, provider switching) |
| `uni/event_loop.py` | Main loop (routing, visual, autonomous, camera, screen) |
| `uni/contracts.py` | Canonical Action/ActionResult/Observation |
| `uni/capabilities/base.py` | Capability contract (only allowed import) |
| `uni/webui/server.py` | WebUI (monolithic, needs split) |
| `uni/desktop/main.js` | Electron main (tray, window, SSE, stop stack) |
| `uni/desktop/renderer/app.js` | Desktop UI v4 (universal engine) |
| `scripts/launcher.js` | Node launcher (dedup, pids.json, flake retry, HTTP :8790) |
| `requirements.txt` | Python deps (needs pyproject.toml + lock) |

---

## ⚠️ Top 5 Risks for Packaging

| # | Risk | Impact |
|---|------|--------|
| 1 | **No dependency lock** (`requirements.txt` only) | Unreproducible builds, version conflicts |
| 2 | **Monolithic webui/server.py** (2600 lines) | Hard to maintain, test, package |
| 3 | **System Python dependency** (`C:\LLM\python312\python.exe`) | Won't work on user machines |
| 4 | **VLM requires torch/GPU** (Gradio Moondream) | No CPU-first fallback |
| 5 | **Launcher is Node.js script** | Not a standalone `.exe` |

---

## 📦 Packaging Critical Path

```
1. pyproject.toml + uv.lock          ← Foundation
2. Split webui/server.py → handlers/  ← Architecture
3. Embed Python 3.12 (embeddable)    ← Distribution
4. Compile launcher.js → UNI-Launcher.exe
5. Integrate moondream.cpp (GGUF)    ← CPU-first VLM
6. NSIS installer + clean VM test    ← Delivery
```

---

## 🧪 Test Commands for Verification

```bash
# Full test suite
pytest -p no:cacheprovider -o asyncio_mode=auto

# Architecture audit
python -m uni.check_architecture --strict

# JS syntax check
node --check uni/desktop/main.js uni/desktop/preload.js uni/desktop/renderer/app.js scripts/launcher.js

# Manual smoke (run after UNI.bat)
curl http://127.0.0.1:8787/api/heartbeats
curl http://127.0.0.1:8787/api/roles
curl -X POST http://127.0.0.1:8787/api/vision/capture -H "Content-Type: application/json" -d '{"image_b64":"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}'
```

---

## 📋 Analysis Files Created

| File | Purpose |
|------|---------|
| `ANALYSIS_PROJECT_OVERVIEW.md` | Full project analysis (architecture, components, issues, recommendations) |
| `ANALYSIS_TECHNICAL_DEBT.md` | Actionable technical debt inventory with sprint plan |
| `ANALYSIS_PACKAGING_GUIDE.md` | Step-by-step packaging guide (Python embed, launcher, NSIS, VM test) |
| `ANALYSIS_SUMMARY.md` | This file — quick reference for external AI |

---

## 🤝 For the Next AI Reviewer

**You have full context now.** The three analysis files + the canonical documents (`UNI_PROJECT_BRIEF.md`, `UNI_CONTEXT.md`, `UNI_MANIFESTO_v2.6.md`) give you everything needed to:

1. **Understand the architecture** — capability isolation, contracts, event loop
2. **Identify what needs fixing** — debt inventory with priorities
3. **Execute packaging** — guide with concrete commands and scripts
4. **Verify correctness** — test commands and acceptance criteria

**Start with:** `UNI_PROJECT_BRIEF.md` → `ANALYSIS_SUMMARY.md` → `ANALYSIS_PACKAGING_GUIDE.md`

---

## 📌 Current Status (2026-08-13)

| Area | Status |
|------|--------|
| Core functionality | ✅ Working (264 tests pass) |
| Architecture compliance | ✅ 0 audit violations |
| WebUI + Desktop | ✅ Live verified |
| Launcher (Node.js) | ✅ Working |
| **Windows installer** | ❌ **NOT DONE** (primary goal) |
| CPU-first VLM | ❌ Requires moondream.cpp |
| Embedded Python | ❌ Uses system Python |
| Dependency lock | ❌ requirements.txt only |
| Clean VM test | ❌ Not automated |

**Next milestone:** `UNI-Setup.exe` that works on a fresh Windows 10/11 x64 VM with zero manual steps.