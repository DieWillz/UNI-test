from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _api():
    try:
        module = importlib.import_module("uni.direction_sync")
    except ModuleNotFoundError:
        pytest.fail("uni.direction_sync is not implemented")
    return module


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    handoffs = tmp_path / "docs" / "handoffs"
    handoffs.mkdir(parents=True)
    master = handoffs / "UNI_MASTER_DIRECTION.md"
    active = handoffs / "UNI_ACTIVE_WORK.md"
    master.write_text("# Master\nrule one\n", encoding="utf-8")
    active.write_text(
        "# Active\n<!-- UNI_ACTIVE_WORK_TOML_BEGIN -->\n```toml\n"
        "schema_version = 1\n"
        '[[assignment]]\nagent = "Agent A"\ntask = "Operator"\nstatus = "ACTIVE"\n'
        'exclusive_paths = ["uni/operator/**"]\nread_only_paths = ["uni/transports/**"]\n'
        'dependencies = ["Master Direction"]\nupdated_at = "2026-09-11T20:00:00Z"\n'
        "```\n<!-- UNI_ACTIVE_WORK_TOML_END -->\n",
        encoding="utf-8",
    )
    state = tmp_path / ".uni-dev" / "coordination" / "direction_ack.json"
    return master, active, state


def test_missing_ack_is_blocked(tmp_path: Path) -> None:
    api = _api()
    master, active, state = _repo(tmp_path)
    gate = api.DirectionSyncGate(master, active, state)
    result = gate.check("Agent A")
    assert result.ok is False
    assert result.reason == "not_acknowledged"