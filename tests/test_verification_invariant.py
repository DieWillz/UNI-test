from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from uni.config import AgentConfig
from uni.contracts import (
    Evidence,
    TaskOutcome,
    TaskStatus,
    Verification,
    VerificationStatus,
)


def test_verified_requires_concrete_evidence() -> None:
    with pytest.raises(ValidationError):
        Verification(status="verified", method="screen")


def test_missing_verification_fails_closed() -> None:
    outcome = TaskOutcome.finalize(command="открой приложение", message="tool returned")
    assert outcome.status is TaskStatus.NOT_VERIFIED
    assert outcome.is_success is False


def test_evidence_allows_verified_terminal_state() -> None:
    verification = Verification(
        status=VerificationStatus.VERIFIED,
        method="read_after_write",
        evidence=[Evidence(source="state.query", summary="postcondition is visible")],
    )
    outcome = TaskOutcome.finalize(
        command="измени состояние",
        message="подтверждено",
        verification=verification,
    )
    assert outcome.status is TaskStatus.VERIFIED
    assert outcome.is_success is True


def test_verification_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(verification_enabled=False)


def test_repository_invariant_checker() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["C:\\LLM\\python312\\python.exe", str(root / "scripts" / "check_verification_invariant.py")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
