from uni.workspace.progress import calculate_progress


def test_progress_five_of_seven_is_71_percent():
    assert calculate_progress(
        acceptance_total=7,
        acceptance_passed=5,
        agent_verified=False,
        owner_verified=False,
    ) == 71


def test_agent_verified_without_owner_approval_is_capped_at_99():
    assert calculate_progress(
        acceptance_total=7,
        acceptance_passed=7,
        agent_verified=True,
        owner_verified=False,
    ) == 99


def test_progress_reaches_100_only_after_all_three_gates():
    assert calculate_progress(7, 7, False, True) == 99
    assert calculate_progress(7, 6, True, True) == 85
    assert calculate_progress(7, 7, True, True) == 100
