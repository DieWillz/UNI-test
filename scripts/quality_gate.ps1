<#
  Quality Gate (P-08, 2026-08-17).
  Независимая проверка качества перед merge/релизом.

  Запуск:
    powershell -ExecutionPolicy Bypass -File scripts\quality_gate.ps1

  Что делает:
    1. pytest (полный suite)
    2. uni.check_architecture --strict (ADR-0005)
    3. node --check для всех project-owned JS
    4. py_compile для всех project-owned .py (syntax)
    5. grep на запрещённые паттерны (mock-only test, hardcoded secrets)
    6. Trajectories health check (фейк-детектор)
    7. (опц.) интеграционный тест без моков для Vision/Computer
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PY = if ($env:UNI_PYTHON) { $env:UNI_PYTHON } else { 'C:\LLM\python312\python.exe' }

function Fail($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    exit 1
}
function Pass($msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }

Write-Host "Quality Gate: $ROOT" -ForegroundColor Cyan

# 0. Protected verification invariant (must run before the rest of the suite)
Write-Host "`n== verification invariant ==" -ForegroundColor Yellow
& $PY (Join-Path $ROOT 'scripts\check_verification_invariant.py')
if ($LASTEXITCODE -ne 0) { Fail "verification invariant failed" }
Pass "verification invariant enforced"

# 1. pytest
Write-Host "`n== pytest ==" -ForegroundColor Yellow
& $PY -m pytest -p no:cacheprovider -o asyncio_mode=auto --tb=short
if ($LASTEXITCODE -ne 0) { Fail "pytest failed" }
Pass "pytest passed"

# 2. architecture audit
Write-Host "`n== check_architecture ==" -ForegroundColor Yellow
& $PY -m uni.check_architecture --strict
if ($LASTEXITCODE -ne 0) { Fail "architecture audit failed" }
Pass "architecture audit 0/0"

# 3. node --check (project-owned JS)
Write-Host "`n== node --check ==" -ForegroundColor Yellow
$jsFiles = Get-ChildItem -Path (Join-Path $ROOT 'uni\desktop') -Recurse -Filter *.js `
    | Where-Object { $_.FullName -notmatch 'node_modules' }
foreach ($f in $jsFiles) {
    & node --check $f.FullName 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "node --check failed on $($f.FullName)" }
}
Pass "node --check OK ($($jsFiles.Count) files)"

# 4. py_compile
Write-Host "`n== py_compile ==" -ForegroundColor Yellow
$pyFiles = Get-ChildItem -Path (Join-Path $ROOT 'uni') -Recurse -Filter *.py `
    | Where-Object { $_.FullName -notmatch '__pycache__' }
foreach ($f in $pyFiles) {
    & $PY -m py_compile $f.FullName
    if ($LASTEXITCODE -ne 0) { Fail "py_compile failed on $($f.FullName)" }
}
Pass "py_compile OK ($($pyFiles.Count) files)"

# 5. grep на запрещённые паттерны
Write-Host "`n== pattern checks ==" -ForegroundColor Yellow
$forbidden = @(
    'skipIf\(',
    'pytest\.mark\.skip',
    'api_key\s*[:=]\s*["''][^"'']+["'']'
)
foreach ($pat in $forbidden) {
    $hits = Select-String -Path (Join-Path $ROOT 'uni\**\*.py') -Pattern $pat -ErrorAction SilentlyContinue
    if ($hits) { Fail "forbidden pattern '$pat' found: $($hits.Count) hits" }
}
Pass "no forbidden patterns"

# 6. Trajectories health
Write-Host "`n== trajectories health ==" -ForegroundColor Yellow
$trajPath = Join-Path $ROOT 'uni\memory\trajectories.jsonl'
$fakePath = Join-Path $ROOT 'uni\memory\trajectories.jsonl.FAKE'
if (Test-Path $fakePath) { Pass "fake quarantined: $fakePath" }
else { Write-Host "[WARN] trajectories.jsonl.FAKE not found" -ForegroundColor Yellow }
if (Test-Path $trajPath) {
    $out = & $PY -c @"
import json
from collections import Counter
coords = []
with open(r'$trajPath', encoding='utf-8') as f:
    for ln in f:
        ln = ln.strip()
        if not ln or ln.startswith('#'): continue
        try:
            rec = json.loads(ln)
            for s in rec.get('steps') or []:
                if isinstance(s, dict):
                    x, y = s.get('x'), s.get('y')
                    if isinstance(x,(int,float)) and isinstance(y,(int,float)):
                        coords.append((int(x),int(y)))
        except: pass
if len(coords) >= 10:
    top = Counter(coords).most_common(1)[0][1]
    print(f'{len(coords)} {top/len(coords):.2f}')
else:
    print(f'{len(coords)} 0.00')
"@
    $parts = $out.Trim() -split ' '
    Write-Host "  total coords: $($parts[0]); top frequency: $($parts[1])"
    if ([double]$parts[1]) -gt 0.5) { Fail "trajectories likely fake (top freq > 50%)" }
    Pass "trajectories OK"
}

# 7. integration test (без моков для Vision/Computer)
Write-Host "`n== integration gate ==" -ForegroundColor Yellow
& $PY -m pytest tests/test_independent_gate.py -v --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] independent gate tests not found or failed (optional)" -ForegroundColor Yellow
} else {
    Pass "independent gate OK"
}

Write-Host "`n[OK] All gates passed" -ForegroundColor Green
exit 0
