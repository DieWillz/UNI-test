from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != "nt", reason="Tk thread teardown is Windows-specific")
def test_many_action_badges_close_without_tcl_native_crash() -> None:
    code = r'''
import gc
import time
from uni.capabilities.human_mouse import HumanMouseController, HumanMouseSettings

items = []
for i in range(20):
    ctrl = HumanMouseController(HumanMouseSettings(show_badge=True, move_duration=0.05))
    ctrl._flash(200 + i, 200, "lifecycle-test")
    items.append(ctrl)
time.sleep(0.2)
for ctrl in items:
    ctrl.close()
items.clear()
for _ in range(5):
    gc.collect()
    time.sleep(0.02)
print("clean-exit")
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (
        f"child crashed: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "clean-exit" in proc.stdout


@pytest.mark.skipif(os.name != "nt", reason="Tk worker is Windows-specific")
def test_many_action_badges_share_one_gui_worker() -> None:
    code = r'''
import threading
import time
from uni.action_badge import UniActionBadge

items = [UniActionBadge() for _ in range(20)]
for i, badge in enumerate(items):
    badge.flash_at(300 + i, 300, "shared-worker-test")
time.sleep(0.4)
count = sum(1 for thread in threading.enumerate()
            if thread.name == "uni-action-badge")
print(f"badge_threads={count}")
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    assert "badge_threads=1" in proc.stdout
