from __future__ import annotations

from pathlib import Path

import pytest

from uni.direction_sync import DirectionSyncError, DirectionSyncGate


def _assignment(
    agent: str,
    task: str,
    exclusive_paths: list[str],
    *,
    read_only_paths: list[str] | None = None,
    dependencies: list[str] | None = None,
    updated_at: str = "2026-09-11T20:00:00Z",
    status: str = "ACTIVE",
) -> str:
    ro = read_only_paths or []
    deps = dependencies or []
    return "".join(
        [
            "[[assignment]]\n",
            f'agent = "{agent}"\n',
            f'task = "{task}"\n',
            f'status = "{status}"\n',
            f"exclusive_paths = {exclusive_paths!r}\n".replace("'", '"'),
            f"read_only_paths = {ro!r}\n".replace("'", '"'),
            f"dependencies = {deps!r}\n".replace("'", '"'),
            f'updated_at = "{updated_at}"\n',
        ]
    )


def _active_doc(*, note: str = "notes may change\n", a_paths: list[str] | None = None) -> str:
    a_paths = a_paths or ["uni/operator/**"]
    block = (
        "schema_version = 1\n"
        + _assignment(
            "Agent A",
            "Operator",
            a_paths,
            read_only_paths=["uni/transports/**"],
            dependencies=["Master Direction"],
        )
        + _assignment(
            "Agent B",
            "Telegram",
            ["uni/transports/**"],
            read_only_paths=["uni/operator/**"],
            dependencies=[],
        )
    )
    return (
        "# Active\n<!-- UNI_ACTIVE_WORK_TOML_BEGIN -->\n```toml\n"
        + block
        + "```\n<!-- UNI_ACTIVE_WORK_TOML_END -->\n"
        + note
    )


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    master = tmp_path / "UNI_MASTER_DIRECTION.md"
    active = tmp_path / "UNI_ACTIVE_WORK.md"
    state = tmp_path / "agent_sync.json"
    master.write_text("# Master\nrule one\n", encoding="utf-8")
    active.write_text(_active_doc(), encoding="utf-8")
    return master, active, state


def test_fresh_agent_without_ack_is_blocked(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    check = DirectionSyncGate(master, active, state).check("Agent A")
    assert check.ok is False
    assert check.reason == "not_acknowledged"


def test_agent_after_ack_is_allowed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    ack = gate.acknowledge("Agent A")
    check = gate.check("Agent A", paths=["uni/operator/runtime.py"])
    assert ack["revision"] == check.revision
    assert check.ok is True
    assert check.reason == "current"


def test_master_change_makes_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    master.write_text("# Master\nrule one\nrule two\n", encoding="utf-8")
    check = gate.check("Agent A")
    assert check.ok is False
    assert check.reason == "stale_direction"


def test_ownership_change_makes_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    active.write_text(_active_doc(a_paths=["uni/operator/**", "uni/control_queue.py"]), encoding="utf-8")
    check = gate.check("Agent A")
    assert check.ok is False
    assert check.reason == "stale_direction"


def test_narrative_note_does_not_make_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    active.write_text(_active_doc(note="different narrative history\n"), encoding="utf-8")
    assert gate.check("Agent A").ok is True


def test_comment_inside_machine_block_does_not_make_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    text = active.read_text(encoding="utf-8")
    text = text.replace("schema_version = 1\n", "schema_version = 1\n# harmless comment\n")
    active.write_text(text, encoding="utf-8")
    assert gate.check("Agent A").ok is True


def test_agent_cannot_write_foreign_exclusive_path(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    check = gate.check("Agent A", paths=["uni/transports/telegram/gateway.py"])
    assert check.ok is False
    assert check.reason == "ownership_conflict"
    assert check.conflicts[0]["owner"] == "Agent B"


def test_agent_own_exclusive_path_is_allowed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    assert gate.check("Agent A", paths=["uni/operator/runtime.py"]).ok is True


def test_unknown_agent_fails_closed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    check = gate.check("Unknown Agent")
    assert check.ok is False
    assert check.reason == "agent_not_assigned"
    with pytest.raises(DirectionSyncError, match="agent_not_assigned"):
        gate.acknowledge("Unknown Agent")


def test_corrupted_active_work_fails_closed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    active.write_text(
        "# Active\n<!-- UNI_ACTIVE_WORK_TOML_BEGIN -->\n```toml\nnot valid = [\n```\n"
        "<!-- UNI_ACTIVE_WORK_TOML_END -->\n",
        encoding="utf-8",
    )
    check = gate.check("Agent A")
    assert check.ok is False
    assert check.reason == "invalid_active_work"


def test_required_assignment_fields_are_fail_closed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    text = active.read_text(encoding="utf-8").replace('dependencies = ["Master Direction"]\n', "", 1)
    active.write_text(text, encoding="utf-8")
    check = DirectionSyncGate(master, active, state).check("Agent A")
    assert check.ok is False
    assert check.reason == "invalid_active_work"


def test_corrupted_ack_state_fails_closed(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    state.write_text("{broken", encoding="utf-8")
    check = DirectionSyncGate(master, active, state).check("Agent A")
    assert check.ok is False
    assert check.reason == "invalid_ack_state"


def test_task_change_makes_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    text = active.read_text(encoding="utf-8").replace('task = "Operator"', 'task = "Operator v2"', 1)
    active.write_text(text, encoding="utf-8")
    assert gate.check("Agent A").reason == "stale_direction"


def test_protected_scope_change_makes_agent_stale(tmp_path: Path) -> None:
    master, active, state = _workspace(tmp_path)
    gate = DirectionSyncGate(master, active, state)
    gate.acknowledge("Agent A")
    text = active.read_text(encoding="utf-8").replace(
        'read_only_paths = ["uni/transports/**"]',
        'read_only_paths = ["uni/transports/**", "uni/devcoord/**"]',
        1,
    )
    active.write_text(text, encoding="utf-8")
    assert gate.check("Agent A").reason == "stale_direction"


def test_cli_returns_nonzero_on_deny(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from uni.direction_sync import main

    master, active, state = _workspace(tmp_path)
    rc = main([
        "--master", str(master), "--active", str(active), "--state", str(state),
        "check", "--agent", "Agent A", "--path", "uni/operator/runtime.py",
    ])
    output = capsys.readouterr().out
    assert rc != 0
    assert "DENIED / NOT_ACKNOWLEDGED" in output
