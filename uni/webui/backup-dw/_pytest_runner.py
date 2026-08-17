"""uni/webui/_pytest_runner.py — фоновый прогон pytest (ADM-02 run_pytest).

Запускается из admin_api._handle_admin_action(action='run_pytest') в фоне.
После завершения пишет runtime/pytest_last.json с passed/failed/время,
чтобы /api/admin/stats отобразил результат (ADM-10: клик → результат в stats).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_RUNTIME = _ROOT / "runtime"
_OUTBOX = _ROOT / "outbox"


def main() -> int:
    import pytest

    xml = _OUTBOX / "HERMES_PYTEST.xml"
    _RUNTIME.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    # прогон; результат считаем по exit code + xml (если есть)
    code = pytest.main(["-q", f"--junitxml={xml}"])
    elapsed = round(time.time() - t0, 1)
    summary = {"status": "done", "returncode": code, "time_s": elapsed,
               "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if xml.is_file():
        try:
            txt = xml.read_text(encoding="utf-8", errors="replace")
            import re
            m = re.search(r'tests="(\d+)"\s+failures="(\d+)"\s+errors="(\d+)"', txt)
            if m:
                total = int(m.group(1)); fails = int(m.group(2)) + int(m.group(3))
                summary["passed"] = total - fails
                summary["failed"] = fails
                summary["total"] = total
        except Exception:
            pass
    (_RUNTIME / "pytest_last.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
