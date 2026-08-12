"""Tests for devcoord Verifier + Applier (extension, not a rewrite).

Run from repo root:
    PYTHONPATH=C:\\LLM\\UNI C:\\LLM\\python312\\python.exe -m pytest tests/test_devcoord_verifier_applier.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uni.devcoord.applier import Applier
from uni.devcoord.coordinator import DevelopmentCoordinator
from uni.devcoord.models import (
    ClaimVerificationResult,
    DevelopmentTask,
    ProviderResult,
    ProviderConfig,
    TaskStatus,
)
from uni.devcoord.providers import ProviderRegistry
from uni.devcoord.store import CoordinationStore
from uni.devcoord.verifier import Verifier

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Verifier — checks real repo facts, not model confidence                    #
# --------------------------------------------------------------------------- #
def test_verifier_true_claim():
    v = Verifier(REPO_ROOT)
    res = v.verify_claim(
        "функция _API_ALIASES уже существует в executors.py",
        file_hint="uni/tools/executors.py",
    )
    assert isinstance(res, ClaimVerificationResult)
    assert res.verified is True
    assert "executors.py" in res.evidence


def test_verifier_false_claim():
    v = Verifier(REPO_ROOT)
    res = v.verify_claim(
        "функция nonexistent_xyz_token_abc уже существует в executors.py",
        file_hint="uni/tools/executors.py",
    )
    assert res.verified is False
    assert "не найден" in res.evidence


def test_verifier_negated_claim():
    v = Verifier(REPO_ROOT)
    res = v.verify_claim(
        "функция nonexistent_xyz_token_abc НЕ существует в executors.py",
        file_hint="uni/tools/executors.py",
    )
    # No match => absence supports the negation.
    assert res.verified is True
    assert "подтверждает отрицательное" in res.evidence


def test_verifier_no_tokens():
    v = Verifier(REPO_ROOT)
    res = v.verify_claim("просто текст без кодовых слов", file_hint="uni/tools/executors.py")
    assert res.verified is False


# --------------------------------------------------------------------------- #
# Coordinator — wires Verifier into result.verified and persists it           #
# --------------------------------------------------------------------------- #
def _make_coordinator(tmp_path: Path, verifier: Verifier | None):
    store = CoordinationStore(tmp_path / "coord.json")
    cfg = ProviderConfig(
        id="stub", display_name="stub", transport="api",
        enabled=True, base_url="http://example/v1", model="x",
    )
    reg = ProviderRegistry([cfg], allow_paid_api=True)
    coord = DevelopmentCoordinator(
        workspace=tmp_path, store=store, providers=reg, verifier=verifier
    )
    return coord, store, reg


@pytest.mark.asyncio
async def test_coordinator_stores_verified(tmp_path: Path):
    verifier = Verifier(REPO_ROOT)
    coord, store, reg = _make_coordinator(tmp_path, verifier)

    task = DevelopmentTask(
        title="t", goal="g", instructions="review the code",
        provider_sequence=["stub"],
        constraints=["verify against real code"],
    )
    coord.create_task(task)

    # Stub the provider's network call.
    provider = reg.build("stub")

    async def fake_request(handoff):  # noqa: ANN001
        return ProviderResult(provider_id="stub", transport="api", content="x")

    provider.request = fake_request

    updated = await coord.run_next(
        task.id, verify_claim="функция _API_ALIASES уже существует в executors.py"
    )
    assert updated.results[-1].verified is not None
    assert updated.results[-1].verified.verified is True

    # Persisted through the store round-trip.
    persisted = store.get_task(task.id)
    assert persisted.results[-1].verified is not None
    assert persisted.results[-1].verified.verified is True


@pytest.mark.asyncio
async def test_coordinator_without_verifier(tmp_path: Path):
    coord, store, reg = _make_coordinator(tmp_path, None)
    task = DevelopmentTask(title="t", goal="g", instructions="review", provider_sequence=["stub"])
    coord.create_task(task)
    provider = reg.build("stub")

    async def fake_request(handoff):  # noqa: ANN001
        return ProviderResult(provider_id="stub", transport="api", content="x")

    provider.request = fake_request
    updated = await coord.run_next(task.id)
    assert updated.results[-1].verified is None


# --------------------------------------------------------------------------- #
# Applier — scratch git repo, assert never-commit / revert-on-fail           #
# --------------------------------------------------------------------------- #
def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)


def _build_scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git(["git", "init", "-q"], str(repo))
    _git(["git", "config", "user.email", "t@t"], str(repo))
    _git(["git", "config", "user.name", "t"], str(repo))
    (repo / "src.txt").write_text("hello\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    _git(["git", "add", "-A"], str(repo))
    _git(["git", "commit", "-q", "-m", "baseline"], str(repo))
    return repo


def _make_patch(repo: Path, mutate) -> str:
    """Apply `mutate(repo)` to the working tree, capture `git diff --cached`."""
    _git(["git", "reset", "-q"], str(repo))
    _git(["git", "checkout", "--", "."], str(repo))
    _git(["git", "clean", "-fdq"], str(repo))
    mutate(repo)
    _git(["git", "add", "-A"], str(repo))
    diff = _git(["git", "diff", "--cached"], str(repo)).stdout
    _git(["git", "reset", "-q"], str(repo))
    _git(["git", "checkout", "--", "."], str(repo))
    _git(["git", "clean", "-fdq"], str(repo))
    return diff


def _branch_exists(repo: Path, branch: str) -> bool:
    return _git(["git", "rev-parse", "--verify", branch], str(repo)).returncode == 0


@pytest.mark.asyncio
async def test_applier_pass_awaits_and_never_commits(tmp_path: Path):
    repo = _build_scratch_repo(tmp_path)
    base_branch = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"], str(repo)).stdout.strip()
    applier = Applier(repo)

    def add_file(r: Path) -> None:
        (r / "feature.txt").write_text("new feature\n", encoding="utf-8")

    patch = _make_patch(repo, add_file)
    res = await applier.apply_and_test("task-pass", patch)

    assert res.status == "awaiting_human_confirmation"
    assert res.tests_passed is True
    assert _branch_exists(repo, "review/task-pass")

    # NEVER committed to the base branch automatically.
    head_msg = _git(["git", "log", "-1", "--pretty=%s", base_branch], str(repo)).stdout.strip()
    assert head_msg == "baseline"

    # Human confirms the merge.
    ok = await applier.confirm_merge("task-pass")
    assert ok is True
    assert _git(["git", "log", "-1", "--pretty=%s", base_branch], str(repo)).stdout.strip().startswith(
        "devcoord: merge review/task-pass"
    )


@pytest.mark.asyncio
async def test_applier_fail_reverts(tmp_path: Path):
    repo = _build_scratch_repo(tmp_path)
    applier = Applier(repo)

    def add_bad_test(r: Path) -> None:
        (r / "tests" / "test_bad.py").write_text(
            "def test_bad():\n    assert False\n", encoding="utf-8"
        )

    patch = _make_patch(repo, add_bad_test)
    res = await applier.apply_and_test("task-fail", patch)

    assert res.status == "reverted"
    assert res.tests_passed is False
    # Branch must be gone after revert.
    assert not _branch_exists(repo, "review/task-fail")
    # Baseline intact.
    assert _git(["git", "log", "-1", "--pretty=%s"], str(repo)).stdout.strip() == "baseline"


@pytest.mark.asyncio
async def test_applier_unapplicable_patch_reverts(tmp_path: Path):
    repo = _build_scratch_repo(tmp_path)
    applier = Applier(repo)
    # A diff whose hunk context does not match the tracked file -> git apply fails.
    bad_patch = (
        "diff --git a/src.txt b/src.txt\n"
        "--- a/src.txt\n"
        "+++ b/src.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-this_line_does_not_exist_in_src\n"
        "+changed\n"
    )
    res = await applier.apply_and_test("task-badpatch", bad_patch)
    assert res.status == "reverted"
    assert not _branch_exists(repo, "review/task-badpatch")
