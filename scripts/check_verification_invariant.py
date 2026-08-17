"""Fail-closed static/runtime check for UNI's verification invariant."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uni.config import AgentConfig  # noqa: E402
from uni.contracts import (  # noqa: E402
    Evidence,
    TaskOutcome,
    TaskStatus,
    Verification,
    VerificationStatus,
)


def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] verification invariant: {message}")


def check_runtime_contract() -> None:
    if "success" in {item.value for item in TaskStatus}:
        fail("TaskStatus contains forbidden terminal status 'success'")
    try:
        Verification(status=VerificationStatus.VERIFIED, method="test")
    except ValidationError:
        pass
    else:
        fail("verified decision was accepted without evidence")
    try:
        AgentConfig(verification_enabled=False)
    except ValidationError:
        pass
    else:
        fail("verification_enabled=False was accepted")
    decision = Verification(
        status=VerificationStatus.VERIFIED,
        method="invariant_self_test",
        reason="contract test",
        evidence=[Evidence(source="checker", summary="fresh contract evidence")],
    )
    outcome = TaskOutcome.finalize(command="self-test", message="ok", verification=decision)
    if outcome.status is not TaskStatus.VERIFIED or not outcome.is_success:
        fail("valid verified evidence did not produce verified outcome")
    unverified = TaskOutcome.finalize(command="self-test", message="action returned")
    if unverified.status is not TaskStatus.NOT_VERIFIED or unverified.is_success:
        fail("missing evidence did not fail closed to not_verified")


def check_config() -> None:
    data = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    if data.get("agent", {}).get("verification_enabled") is not True:
        fail("config.yaml must set agent.verification_enabled: true")


def check_sources() -> None:
    protected = [
        ROOT / "uni" / "event_loop.py",
        ROOT / "uni" / "tools" / "visual_action.py",
        ROOT / "uni" / "capabilities" / "computer_vision_agent.py",
        ROOT / "uni" / "autonomous_session.py",
        ROOT / "uni" / "webui" / "handlers" / "mission.py",
        ROOT / "uni" / "webui" / "server.py",
    ]
    forbidden = (
        '"status": "success"',
        "'status': 'success'",
        'status="success"',
        '"task.done"',
        "'task.done'",
        '"mission.completed"',
        "'mission.completed'",
    )
    for path in protected:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                fail(f"{path.relative_to(ROOT)} contains forbidden marker {marker!r}")


def main() -> int:
    check_runtime_contract()
    check_config()
    check_sources()
    print("[PASS] COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED invariant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
