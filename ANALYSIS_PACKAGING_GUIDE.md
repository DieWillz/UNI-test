# UNI — Packaging Guide for Windows Distribution

**Target:** `UNI-Setup.exe` + `UNI-Portable.zip` for Windows 10/11 x64  
**Python:** 3.12 (mandatory)  
**Architecture:** x64 only (llama.cpp binaries are x64)

---

## 1. Distribution Architecture

```
UNI-Setup.exe (NSIS/Inno Setup)
│
├─ Embedded Python 3.12
│   └─ python312._pth → site-packages vendored
│
├─ UNI-Launcher.exe (compiled from scripts/launcher.js via pkg/nexe)
│   └─ cloudflared.exe (bundled)
│
├─ runtime/
│   ├─ llama/
│   │   ├─ llama-server.exe (from llama-b10375-bin-win-cpu-x64.zip)
│   │   ├─ ggml*.dll, ggml-cuda.dll, ggml-rpc*.dll, libomp140.x86_64.dll
│   │   └─ (CUDA/ROcm variants in subdirs for GPU profile)
│   └─ tts-webui/ (optional, if UNI_TTS_AUTOSTART=1)
│
├─ uni/ (canonical Python package)
│   ├─ __main__.py, agent.py, brain.py, config.py, contracts.py, event_loop.py
│   ├─ capabilities/, council/, devcoord/, desktop/, webui/, roles/, assets/
│   └─ check_architecture.py
│
├─ downloads/
│   └─ Qwen3-8B-Q4_K_M.gguf (bundled model, ~4.5GB)
│
├─ uni.ico
├─ config.yaml (template, user writes to %APPDATA%\UNI\config.yaml)
└─ UNI.bat (entry point, calls UNI-Launcher.exe)
```

---

## 2. Python Embedding Strategy

### Option A: Official Embeddable Package (Recommended)
```powershell
# 1. Download python-3.12.0-embed-amd64.zip from python.org
# 2. Extract to UNI/python/
# 3. Create python312._pth:
#    .
#    Lib
#    Lib/site-packages
# 4. Vendor all dependencies:
pip install --target=UNI/python/Lib/site-packages -r requirements.txt
# 5. Add unicode support: copy python312.dll + python312._pth to app dir
```

**Pros:** Minimal (~15MB), no registry, no PATH pollution  
**Cons:** No `pip`/`venv` at runtime (fine — we vendor everything)

### Option B: PyInstaller + System Python (Fallback)
```bash
pyinstaller --onedir --noconsole \
  --add-data "uni;uni" \
  --add-data "config.yaml;." \
  --add-data "downloads/Qwen3-8B-Q4_K_M.gguf;downloads" \
  --add-data "uni/assets/voices;uni/assets/voices" \
  --hidden-import=pkg_resources \
  --hidden-import=piper_phonemize \
  --hidden-import=faster_whisper \
  --hidden-import=gradio_client \
  --hidden-import=playwright \
  --hidden-import=comtypes \
  --hidden-import=win32clipboard \
  --hidden-import=win32gui \
  --hidden-import=win32api \
  --hidden-import=win32process \
  --hidden-import=win32con \
  --hidden-import=sounddevice \
  --hidden-import=soundfile \
  --hidden-import=opencv \
  --hidden-import=imagehash \
  --hidden-import=PIL \
  --hidden-import=rich \
  --hidden-import=pydantic \
  --hidden-import=pydantic_settings \
  --hidden-import=yaml \
  --hidden-import=openai \
  --hidden-import=torch \
  --hidden-import=numpy \
  --runtime-hook=runtime_hook.py \
  uni/__main__.py
```

**runtime_hook.py:**
```python
import sys, os
# Ensure vendored packages are on path
sys.path.insert(0, os.path.join(sys._MEIPASS, 'uni'))
sys.path.insert(0, os.path.join(sys._MEIPASS, 'Lib', 'site-packages'))
# Fix config.yaml path
os.environ['UNI_CONFIG'] = os.path.join(os.getenv('APPDATA'), 'UNI', 'config.yaml')
```

### Dependency Extras (pyproject.toml)
```toml
[project]
name = "uni"
version = "1.0.0"
requires-python = "==3.12.*"
dependencies = [
    "pydantic>=2.6",
    "pydantic-settings>=2.1",
    "pyyaml>=6.0",
    "openai>=1.30",
    "playwright>=1.40",
    "pyautogui>=0.9",
    "comtypes>=1.2",
    "opencv-python>=4.10,<5",
    "faster-whisper>=1.0",
    "piper-tts>=1.2",
    "sounddevice>=0.4",
    "soundfile>=0.12",
    "pillow>=10.0",
    "rich>=13.0",
    "gradio-client>=1.3",
]

[project.optional-dependencies]
cpu = ["torch>=2.0,<3.0 --index-url https://download.pytorch.org/whl/cpu"]
cuda = ["torch>=2.0,<3.0 --index-url https://download.pytorch.org/whl/cu124"]
rocm = ["torch>=2.0,<3.0 --index-url https://download.pytorch.org/whl/rocm7.1"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.5", "mypy>=1.10"]
```

**Lock file:** `uv lock` → `uv.lock` (commit to repo)

---

## 3. Launcher Compilation (Node.js → .exe)

### Using `pkg` (simpler, larger binary ~60MB)
```bash
cd C:\LLM\UNI
npm init -y
npm install pkg --save-dev
# package.json:
#   "bin": "scripts/launcher.js",
#   "pkg": { "assets": ["runtime/llama/**/*", "uni/webui/bin/cloudflared.exe"], "targets": ["node20-win-x64"] }
npx pkg scripts/launcher.js --out-path dist/ --target node20-win-x64
# → dist/launcher.exe (rename to UNI-Launcher.exe)
```

### Using `nexe` (smaller, faster startup)
```bash
npm install nexe --save-dev
npx nexe scripts/launcher.js --target windows-x64-20.0.0 --output dist/UNI-Launcher.exe
```

**Required assets to bundle:**
- `runtime/llama/llama-server.exe` + all DLLs
- `uni/webui/bin/cloudflared.exe` (download from Cloudflare)
- `runtime/tts-webui/start_windows.bat` (if TTS autostart)

**Launcher must:**
1. Read `config.yaml` from `%APPDATA%\UNI\config.yaml`
2. Write `runtime/pids.json` to `%LOCALAPPDATA%\UNI\runtime\pids.json`
3. Logs to `%LOCALAPPDATA%\UNI\runtime\logs\`
4. Model path: `%LOCALAPPDATA%\UNI\downloads\Qwen3-8B-Q4_K_M.gguf` (or bundled)

---

## 4. CPU-First VLM Integration

### Current: Gradio Moondream (requires torch, GPU preferred)
### Target: `moondream.cpp` via llama.cpp (GGUF, CPU-native)

**Integration steps:**
1. Download `moondream-2b-int8.gguf` (~1.7GB) → `downloads/`
2. Extend `VisionConfig` in `config.py`:
   ```python
   vlm_provider: str = "llamacpp"  # "gradio" | "openai" | "llamacpp"
   vlm_model: str = "moondream-2b-int8.gguf"
   vlm_base_url: str = "http://127.0.0.1:1235/v1"  # reuse llama.cpp server
   ```
3. Update `VisionCapability._ask()` to use llama.cpp vision endpoint
4. Add fallback chain: `llamacpp` → `gradio` → `openai` → `local_fallback`

**Benefits:**
- Single llama.cpp server for LLM + VLM (port 1235)
- No torch dependency
- CPU-first, honest GPU acceleration via `-ngl` layers

---

## 5. NSIS Installer Script (Outline)

```nsis
!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "UNI"
OutFile "UNI-Setup.exe"
InstallDir "$LOCALAPPDATA\UNI"
RequestExecutionLevel user

!define MUI_ICON "uni.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "English"

Section "Core"
  SetOutPath "$INSTDIR"
  File /r "python\*"           ; Embedded Python
  File /r "uni\*"              ; Canonical package
  File /r "runtime\*"          ; llama.cpp + tts-webui
  File "downloads\Qwen3-8B-Q4_K_M.gguf"
  File "UNI-Launcher.exe"
  File "cloudflared.exe"
  File "UNI.bat"
  File "config.yaml.template"
  File "uni.ico"
  
  ; Create shortcuts
  CreateDirectory "$SMPROGRAMS\UNI"
  CreateShortcut "$SMPROGRAMS\UNI\UNI.lnk" "$INSTDIR\UNI.bat" "" "$INSTDIR\uni.ico"
  CreateShortcut "$DESKTOP\UNI.lnk" "$INSTDIR\UNI.bat" "" "$INSTDIR\uni.ico"
  
  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "GPU Support (CUDA)" SectionCUDA
  ; Optional: install CUDA llama.cpp binaries
  ; File /r "runtime\llama\cuda\*"
SectionEnd

Section "GPU Support (ROCm)" SectionROCm
  ; Optional: install ROCm llama.cpp binaries
SectionEnd

Function .onInit
  ; Check Windows 10/11 x64
  ${IfNot} ${AtLeastWin10} ${OrIf} ${RunningX64} <> 1
    MessageBox MB_ICONSTOP "UNI requires Windows 10/11 x64"
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  Delete "$INSTDIR\*.*"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\UNI\*.*"
  RMDir "$SMPROGRAMS\UNI"
  Delete "$DESKTOP\UNI.lnk"
  ; Clean %APPDATA%\UNI and %LOCALAPPDATA%\UNI (ask user)
SectionEnd
```

---

## 6. Portable Package (UNI-Portable.zip)

```
UNI-Portable/
├─ UNI.bat                    → calls UNI-Launcher.exe --portable
├─ UNI-Launcher.exe           (compiled)
├─ cloudflared.exe
├─ python/                    (embedded)
├─ uni/                       (canonical)
├─ runtime/                   (llama.cpp + tts-webui)
├─ downloads/
│   └─ Qwen3-8B-Q4_K_M.gguf
├─ config.yaml                (template, copied to runtime on first run)
├─ uni.ico
└─ README.txt
```

**UNI.bat for portable:**
```bat
@echo off
set UNI_PORTABLE=1
set APPDATA=%~dp0runtime\appdata
set LOCALAPPDATA=%~dp0runtime\localappdata
mkdir %APPDATA%\UNI 2>nul
mkdir %LOCALAPPDATA%\UNI 2>nul
if not exist "%APPDATA%\UNI\config.yaml" copy config.yaml "%APPDATA%\UNI\config.yaml"
UNI-Launcher.exe %*
```

---

## 7. Clean VM Acceptance Test (Automated)

### Test Script: `tests/packaging/test_clean_vm.ps1`
```powershell
param(
    [string]$InstallerPath = "..\..\dist\UNI-Setup.exe",
    [switch]$PortableMode
)

# 1. Fresh VM snapshot (assumed)
# 2. Install
if (-not $PortableMode) {
    & $InstallerPath /S /D=%LOCALAPPDATA%\UNI
    $launcher = "$env:LOCALAPPDATA\UNI\UNI-Launcher.exe"
} else {
    Expand-Archive "..\..\dist\UNI-Portable.zip" -DestinationPath "$env:TEMP\UNI-Portable"
    $launcher = "$env:TEMP\UNI-Portable\UNI-Launcher.exe"
}

# 3. Start headless
$proc = Start-Process -FilePath $launcher -ArgumentList "--headless" -PassThru -WindowStyle Hidden
Start-Sleep 15  ; wait for stack to come up

# 4. Health checks
function Test-Endpoint($url, $desc) {
    try {
        $r = Invoke-RestMethod -Uri $url -TimeoutSec 10
        Write-Host "✅ $desc: $($r | ConvertTo-Json -Depth 2)"
        return $true
    } catch {
        Write-Host "❌ $desc: $($_.Exception.Message)"
        return $false
    }
}

$ok = $true
$ok = Test-Endpoint "http://127.0.0.1:8787/api/uni/status" "Stack status" -and $ok
$ok = Test-Endpoint "http://127.0.0.1:1235/v1/models" "LLM models" -and $ok

# 5. Chat test
$chat = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/chat" -Method POST `
    -ContentType "application/json" -Body '{"text":"Say hello in Russian"}' -TimeoutSec 30
$ok = ($chat.reply -match "привет|здравств") -and $ok

# 6. Vision capture test (1x1 PNG base64)
$png1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
$vision = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/vision/capture" -Method POST `
    -ContentType "application/json" -Body "{\"image_b64\":\"$png1x1\"}" -TimeoutSec 10
$ok = ($vision.success -eq $true) -and $ok

# 7. Stop stack
Invoke-RestMethod -Uri "http://127.0.0.1:8790/api/launcher/stop" -Method POST -TimeoutSec 10
Start-Sleep 3

# 8. Verify no residual processes
$procs = @("llama-server", "python", "node", "electron", "cloudflared")
foreach ($p in $procs) {
    if (Get-Process -Name $p -ErrorAction SilentlyContinue) {
        Write-Host "❌ Residual process: $p"
        $ok = $false
    }
}

# 9. Result
if ($ok) { Write-Host "🎉 ALL TESTS PASSED"; exit 0 }
else { Write-Host "💥 TESTS FAILED"; exit 1 }
```

**Run in CI:**
```yaml
# .github/workflows/packaging-test.yml
jobs:
  clean-vm-test:
    runs-on: windows-2022
    steps:
      - uses: actions/checkout@v4
      - name: Build installer
        run: .\build_installer.ps1
      - name: Run clean VM test
        run: .\tests\packaging\test_clean_vm.ps1 -InstallerPath dist\UNI-Setup.exe
```

---

## 8. Configuration Management for Packaged App

### Config Locations (Priority Order)
1. `%APPDATA%\UNI\config.yaml` (user writable, survives updates)
2. `%LOCALAPPDATA%\UNI\config.yaml` (fallback)
3. Bundled `config.yaml.template` (read-only defaults)

### Launcher Config Injection
```javascript
// In launcher.js before spawning webui:
const userConfig = path.join(os.homedir(), 'AppData', 'Roaming', 'UNI', 'config.yaml');
const localConfig = path.join(os.homedir(), 'AppData', 'Local', 'UNI', 'config.yaml');
const env = { ...process.env, UNI_CONFIG: fs.existsSync(userConfig) ? userConfig : localConfig };
```

### Python Config Loading (uni/config.py)
```python
def load_config(path: str = "config.yaml") -> Config:
    # Allow env override
    import os
    env_path = os.environ.get("UNI_CONFIG")
    if env_path and Path(env_path).exists():
        path = env_path
    # ... rest unchanged
```

---

## 9. GPU Profile Handling

### Installer Components
```
Core (always):
  - llama-b10375-bin-win-cpu-x64.zip → runtime/llama/

CUDA (optional section):
  - llama-b10375-bin-win-cuda-12.4-x64.zip → runtime/llama/cuda/

ROCm (optional section):
  - llama-b10375-bin-win-rocm-7.14-x64.zip → runtime/llama/rocm/
```

### Launcher Auto-Detect
```javascript
function detectGpu() {
  try {
    const out = execSync('nvidia-smi --query-gpu=name --format=csv,noheader', {encoding: 'utf8'});
    if (out.trim()) return 'cuda';
  } catch {}
  try {
    const out = execSync('rocminfo', {encoding: 'utf8'});
    if (out.includes('Agent')) return 'rocm';
  } catch {}
  return 'cpu';
}

// Use appropriate binary
const llamaBin = {
  cuda: 'runtime/llama/cuda/llama-server.exe',
  rocm: 'runtime/llama/rocm/llama-server.exe',
  cpu: 'runtime/llama/llama-server.exe'
}[gpuType];
```

---

## 10. Checklist for Release

- [ ] `pyproject.toml` + `uv.lock` committed
- [ ] All dead code removed (`agents/uni*`, `UNI-reuse-candidates/`, copy files)
- [ ] `uni/webui/server.py` modularized
- [ ] `EventLoop` split into focused modules
- [ ] `ActionResult` migration complete
- [ ] CPU-first VLM (moondream.cpp) integrated
- [ ] Embedded Python 3.12 tested
- [ ] `UNI-Launcher.exe` compiled + tested
- [ ] NSIS installer builds + installs + uninstalls cleanly
- [ ] Portable zip works on clean VM
- [ ] Clean VM acceptance test passes (headless)
- [ ] Code signing certificate configured
- [ ] Auto-update mechanism implemented
- [ ] Documentation: `PACKAGING.md`, `INSTALL.md`, `UNINSTALL.md`

---

## 11. Estimated Effort

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| Foundation (deps, cleanup, modularization) | 2 weeks | Modular codebase, lock file |
| Python embedding + launcher compilation | 1 week | `UNI-Launcher.exe`, embedded Python |
| VLM integration + installer | 2 weeks | CPU-first VLM, NSIS installer |
| Testing + polish + signing | 1 week | Clean VM test passing, signed binaries |
| **Total** | **~6 weeks** | **`UNI-Setup.exe` ready for users** |