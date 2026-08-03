"""Tests for the Knowledge Base (uni.knowledge.base).

Run:
    PYTHONPATH=C:\\LLM\\UNI C:\\LLM\\python312\\python.exe -m pytest tests/test_knowledge_base.py -q
"""
from __future__ import annotations

from pathlib import Path

from uni.knowledge.base import (
    CouncilResponse,
    KnowledgeBase,
    Skill,
    VerifiedClaim,
)


def _kb(tmp_path: Path) -> KnowledgeBase:
    return KnowledgeBase(tmp_path / "knowledge.db")


def test_store_and_retrieve_response(tmp_path: Path):
    kb = _kb(tmp_path)
    resp = CouncilResponse(
        response_id="R1",
        task_id="T1",
        provider="groq",
        topic="add retry to brain",
        response_text="Wrap the call in tenacity.retry with exponential backoff.",
        confidence=0.7,
    )
    kb.store_response(resp)
    # find_similar_responses returns only verified rows, so mark it verified.
    kb.store_response(resp.model_copy(update={"verified": True}))
    similar = kb.find_similar_responses("retry brain", limit=5)
    assert any(r.response_id == "R1" for r in similar)
    # The stored row round-trips unchanged.
    assert similar[0].provider == "groq"
    assert similar[0].topic == "add retry to brain"


def test_find_similar_filters_by_keywords(tmp_path: Path):
    kb = _kb(tmp_path)
    kb.store_response(
        CouncilResponse(
            response_id="A", task_id="T1", provider="groq",
            topic="add retry to brain",
            response_text="use tenacity retry", confidence=0.6,
        )
    )
    kb.store_response(
        CouncilResponse(
            response_id="B", task_id="T2", provider="claude",
            topic="add logging to agent",
            response_text="use structlog for structured logs", confidence=0.6,
        )
    )
    # Mark both verified so find_similar_responses can return them, then filter.
    kb.store_response(
        CouncilResponse(response_id="A", task_id="T1", provider="groq",
                        topic="add retry to brain", response_text="use tenacity retry",
                        confidence=0.6, verified=True)
    )
    kb.store_response(
        CouncilResponse(response_id="B", task_id="T2", provider="claude",
                        topic="add logging to agent",
                        response_text="use structlog for structured logs",
                        confidence=0.6, verified=True)
    )
    hits = kb.find_similar_responses("retry", limit=10)
    ids = {h.response_id for h in hits}
    assert "A" in ids
    assert "B" not in ids  # no keyword overlap with "retry"


def test_mark_used_in_patch(tmp_path: Path):
    kb = _kb(tmp_path)
    kb.store_response(
        CouncilResponse(
            response_id="R1", task_id="T1", provider="groq",
            topic="add retry", response_text="tenacity retry", confidence=0.7,
        )
    )
    kb.store_response(
        CouncilResponse(response_id="R1", task_id="T1", provider="groq",
                        topic="add retry", response_text="tenacity retry",
                        confidence=0.7, verified=True)
    )
    kb.mark_used_in_patch("R1", success=True)
    hits = kb.find_similar_responses("retry", limit=10)
    assert hits[0].used_in_patch is True
    assert hits[0].patch_success is True


def test_extract_skill(tmp_path: Path):
    kb = _kb(tmp_path)
    skill = kb.extract_skill(
        task_id="T1",
        patch_diff="--- a/uni/brain.py\n+++ b/uni/brain.py\n@@\n+import tenacity",
        skill_name="retry_wrapper",
        description="Wrap LLM calls with tenacity retry.",
    )
    assert isinstance(skill, Skill)
    assert skill.source_task_ids == ["T1"]
    assert skill.success_count == 1
    # Persisted and retrievable, sorted by success_count.
    top = kb.get_top_skills(limit=10)
    assert top and top[0].skill_id == skill.skill_id


def test_get_top_skills_ordering(tmp_path: Path):
    kb = _kb(tmp_path)
    low = kb.extract_skill("T1", "diff1", "low", "low skill")
    high_a = kb.extract_skill("T2", "diff2", "high_a", "high skill A")
    high_b = kb.extract_skill("T3", "diff3", "high_b", "high skill B")
    # All three are distinct skills (one row each). Sort by success_count desc,
    # then by created_at desc -> the two high skills (count 1) rank above low.
    top = kb.get_top_skills(limit=10)
    names = [s.name for s in top]
    assert "low" not in names[:2]
    assert low.skill_id in {s.skill_id for s in top}
    assert high_a.skill_id in {s.skill_id for s in top}
    assert high_b.skill_id in {s.skill_id for s in top}


def test_store_and_get_claims(tmp_path: Path):
    kb = _kb(tmp_path)
    claim = VerifiedClaim(
        claim_id="C1",
        claim_text="_API_ALIASES exists in executors.py",
        file_path="uni/tools/executors.py",
        verified=True,
        evidence="matched at executors.py:57",
    )
    kb.store_claim(claim)
    claims = kb.get_claims_for_file("uni/tools/executors.py")
    assert len(claims) == 1
    assert claims[0].claim_id == "C1"
    assert claims[0].verified is True
    # A different file returns nothing.
    assert kb.get_claims_for_file("uni/other.py") == []
