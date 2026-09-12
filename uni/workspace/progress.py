from __future__ import annotations


def calculate_progress(
    acceptance_total: int,
    acceptance_passed: int,
    agent_verified: bool,
    owner_verified: bool,
) -> int:
    """Return fail-closed task progress from acceptance and verification gates."""
    if acceptance_total <= 0:
        return 0

    passed = min(max(acceptance_passed, 0), acceptance_total)
    acceptance_complete = passed == acceptance_total
    if acceptance_complete and agent_verified and owner_verified:
        return 100

    acceptance_percent = (passed * 100) // acceptance_total
    return min(acceptance_percent, 99)
