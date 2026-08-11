#!/usr/bin/env python3
"""B-07 Регрессия: 10× smoke + 3× integration, сводный отчёт.

Запускает pytest для tests/test_regression_smoke.py (parametrize ×10) и
tests/test_regression_integration.py (3 сценария), собирает результаты и
пишет отчёт в UNI_REGRESSION_REPORT.md / .json.

НЕ правит продакшен-код — только прогоняет тесты и отчитывается.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_MD = ROOT / "UNI-mcp-server" / "UNI_REGRESSION_REPORT.md"
REPORT_JSON = ROOT / "UNI-mcp-server" / "UNI_REGRESSION_REPORT.json"


def _run(label: str, args: list[str]) -> dict:
    cmd = [
        sys.executable, "-m", "pytest", *args,
        "-q", "--no-header",
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"label": label, "passed": 0, "failed": 0, "error": "timeout", "rc": -1}
    out = proc.stdout + proc.stderr
    passed = failed = 0
    for line in out.splitlines():
        if "passed" in line and "failed" not in line.split(" passed")[0]:
            # парсим "X passed, Y failed"
            pass
    # простой парсинг итоговой строки
    for line in out.splitlines():
        if "passed" in line and ("failed" in line or "warning" in line):
            # "12 passed, 3 failed" или "12 passed, 2 warnings"
            parts = line.split(",")
            for p in parts:
                p = p.strip()
                if p.endswith("passed"):
                    passed = int(p.split()[0])
                elif p.endswith("failed"):
                    failed = int(p.split()[0])
            break
    return {
        "label": label,
        "passed": passed,
        "failed": failed,
        "rc": proc.returncode,
        "error": None if proc.returncode == 0 else "non-zero exit",
    }


def main() -> int:
    print("=== B-07 Регрессия: 10x smoke + 3x integration ===")
    smoke = _run("smoke", ["tests/test_regression_smoke.py"])
    integ = _run("integration", ["tests/test_regression_integration.py"])

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    report = {
        "generated_at": now,
        "suite": "B-07 regression",
        "smoke": smoke,
        "integration": integ,
        "total_passed": smoke["passed"] + integ["passed"],
        "total_failed": smoke["failed"] + integ["failed"],
        "status": "green" if (smoke["failed"] == 0 and integ["failed"] == 0) else "red",
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = f"""# UNI_REGRESSION_REPORT (B-07)

_Сгенерирован: {now}_

## Статус: {'✅ GREEN' if report['status'] == 'green' else '❌ RED'}

## 10× Smoke (импорт/инициализация ключевых модулей)
- passed: {smoke['passed']}
- failed: {smoke['failed']}
- exit: {smoke['rc']}

## 3× Integration (сценарии act_on_screen)
- passed: {integ['passed']}
- failed: {integ['failed']}
- exit: {integ['rc']}

## Итого
- total passed: {report['total_passed']}
- total failed: {report['total_failed']}

## Как запустить вручную
```
cd C:\\LLM\\UNI
PYTHONPATH=C:\\LLM\\UNI UNI_NO_DISPLAY_CALIBRATION=1 C:\\LLM\\python312\\python.exe -m pytest tests/test_regression_smoke.py tests/test_regression_integration.py -q
```
"""
    REPORT_MD.write_text(md, encoding="utf-8")

    print(f"smoke: {smoke['passed']} passed / {smoke['failed']} failed")
    print(f"integration: {integ['passed']} passed / {integ['failed']} failed")
    print(f"status: {report['status']}")
    print(f"report: {REPORT_MD}")
    return 0 if report["status"] == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
