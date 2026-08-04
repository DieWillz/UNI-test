"""Deterministic pytest check: Config has no dangerous default fields.

Mirrors the assertion in verify_config_defaults.py but as a collectable,
network-free pytest test so `pytest` can verify the claim.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uni.config import Config

_DANGEROUS = ("debug", "allow_camera", "allow_screenshot")


def test_no_dangerous_default_fields():
    missing = [f for f in _DANGEROUS if f in Config.model_fields]
    assert not missing, f"Config содержит опасные поля: {missing}"
