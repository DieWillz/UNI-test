# UNI — Technical Debt Inventory

**Generated:** 2026-08-13  
**Purpose:** Actionable list for refactoring/packaging work

---

## 🔴 Critical (Blocks Packaging)

| ID | Component | Issue | Effort | Fix |
|----|-----------|-------|--------|-----|
| TD-001 | `uni/webui/server.py` | 2600 lines, all routes in one file, sync/async mixing | 3-5 days | Split into `handlers/` + middleware + SSE module |
| TD-002 | `requirements.txt` only | No lock file, no extras (cpu/cuda/rocm), no pyproject.toml | 1 day | Add `pyproject.toml` with `uv`/`poetry`, define extras |
| TD-003 | Python runtime | Uses hardcoded `C:\LLM\python312\python.exe` | 2-3 days | Embed Python 3.12 (embeddable package + pyinstaller) |
| TD-004 | VLM dependency | Gradio Moondream requires torch + GPU; no CPU fallback | 2-3 days | Integrate `moondream.cpp` (GGUF) via llama.cpp |
| TD-005 | Launcher | Node.js script, not .exe | 1-2 days | Compile with `pkg`/`nexe` → `UNI-Launcher.exe` |
| TD-006 | Installer | None | 3-5 days | NSIS/Inno Setup + clean VM acceptance test |

---

## 🟠 High (Architecture)

| ID | Component | Issue | Effort | Fix |
|----|-----------|-------|--------|-----|
| TD-010 | `uni/event_loop.py` | 950 lines, handles routing, visual, autonomous, camera, screen, exploration | 3-4 days | Split into focused modules (see recommendations) |
| TD-011 | Capability contracts | Still return legacy `ToolResult` instead of `ActionResult` | 2-3 days | Migrate all 7 capabilities + ToolExecutor + EventLoop |
| TD-012 | Dual desktop | `uni/webui/desktop/` (legacy) + `uni/desktop/` (canonical) | 0.5 day | Remove `uni/webui/desktop/`, update launcher |
| TD-013 | Config validation | Unknown YAML fields silently ignored | 1 day | Strict Pydantic config + startup validation errors |
| TD-014 | Hardcoded paths | Multiple files reference `C:\LLM\UNI` explicitly | 1 day | Use `_ROOT = Path(__file__).resolve().parents[1]` pattern consistently |

---

## 🟡 Medium (Code Quality)

| ID | Component | Issue | Effort | Fix |
|----|-----------|-------|--------|-----|
| TD-020 | Dead code | `agents/uni*`, `UNI-reuse-candidates/`, copy files (`app — копия.js`, `style — копия.css`) | 0.5 day | Archive or delete; keep only canonical `uni/` |
| TD-021 | `scripts/start_llm.bat.deprecated` | Deprecated launcher shim | 0.1 day | Delete |
| TD-022 | Secret handling | Regex redaction only; no secret scanning in CI | 1 day | Add `trufflehog`/`gitleaks` to CI; use env vars for all keys |
| TD-023 | Health checks | Scattered, no aggregated endpoint | 1 day | Add `/api/health` aggregating all component statuses |
| TD-024 | Logging | Text-only, no structured JSON option | 1 day | Add JSON log format + OpenTelemetry traces |
| TD-025 | Type hints | Partial; some `Any` in critical paths | 2 days | Full type coverage + `mypy --strict` in CI |

---

## 🟢 Low (Nice to Have)

| ID | Component | Issue | Effort | Fix |
|----|-----------|-------|--------|-----|
| TD-030 | Internationalization | All Russian strings hardcoded | 3-5 days | Extract to message catalogs (gettext/fluent) |
| TD-031 | Plugin system | Capabilities hard-registered in `agent.py` | 2-3 days | Entry-point discovery (`importlib.metadata`) |
| TD-032 | GPU profiles | Manual CUDA/ROCm selection | 1 day | Auto-detect in launcher + truthful CPU fallback |
| TD-033 | API docs | No OpenAPI/Swagger for WebUI | 1 day | Generate from handler docstrings |
| TD-034 | Pre-commit | None configured | 0.5 day | `ruff`, `black`, `isort`, `eslint`, `prettier`, architecture check |

---

## 📦 Packaging-Specific Debt

| ID | Area | Current | Target | Effort |
|----|------|---------|--------|--------|
| PKG-001 | Python distribution | System Python 3.12 | Embedded python-3.12-embed + vendored deps | 3 days |
| PKG-002 | llama.cpp binary | `downloads/llama-b10375-bin-win-*.zip` | Bundled in installer, verified checksum | 1 day |
| PKG-003 | Piper voice | `downloads/ru_RU-irina-medium.onnx` + `uni/assets/voices/` | Bundled, single source | 0.5 day |
| PKG-004 | Electron | `node_modules/electron` in `uni/desktop/` | Packaged via `electron-builder` or bundled in NSIS | 2 days |
| PKG-005 | Node.js launcher | `scripts/launcher.js` + `node.exe` | `UNI-Launcher.exe` (pkg/nexe) | 2 days |
| PKG-006 | Cloudflared | `uni/webui/bin/cloudflared.exe` (missing) | Bundled or optional download | 1 day |
| PKG-007 | Uninstaller | None | Proper uninstall (remove files, registry, shortcuts) | 1 day |
| PKG-008 | Code signing | None | EV certificate + timestamp server | 1 day (cert procurement) |
| PKG-009 | Auto-update | None | GitHub Releases + background update check | 2 days |
| PKG-010 | Portable mode | Not tested | `UNI-Portable.zip` (no installer, self-contained) | 1 day |

---

## 🧪 Test Coverage Gaps

| Area | Current | Needed |
|------|---------|--------|
| Camera E2E | Mock only | Real device test (CI: skip if no camera) |
| Council browser | Manual only | Headless Chromium + test accounts (or mock transport) |
| XToys device | Hardware required | Mock server for integration tests |
| Autonomous mode | Unit only | E2E with mocked vision/device |
| Packaging | None | Clean VM script (PowerShell + pytest) |
| Upgrade/downgrade | None | Install v1 → upgrade → verify data migration |

---

## 🎯 Suggested Sprint Plan

### Sprint 1 (Week 1): Foundation
- [ ] TD-002: `pyproject.toml` + lock file
- [ ] TD-020: Remove dead code
- [ ] TD-012: Remove dual desktop
- [ ] TD-013: Strict config validation

### Sprint 2 (Week 2): WebUI Modularization
- [ ] TD-001: Split `server.py` → `handlers/` + middleware
- [ ] TD-023: Aggregated health endpoint
- [ ] TD-024: Structured logging option

### Sprint 3 (Week 3): Contracts + EventLoop
- [ ] TD-011: Full `ActionResult` migration
- [ ] TD-010: Split `event_loop.py`

### Sprint 4 (Week 4): Packaging Core
- [ ] TD-003: Embed Python runtime
- [ ] TD-005: `UNI-Launcher.exe` from Node.js
- [ ] PKG-001/002/003: Bundle assets

### Sprint 5 (Week 5): VLM + Installer
- [ ] TD-004: CPU-first VLM (moondream.cpp)
- [ ] PKG-004/006: Electron + cloudflared bundling
- [ ] TD-006: NSIS installer + clean VM test

### Sprint 6 (Week 6): Polish
- [ ] PKG-007/008/009: Uninstaller, signing, auto-update
- [ ] TD-022: Secret scanning CI
- [ ] TD-025: Full type hints + mypy
- [ ] Documentation: API docs, packaging guide