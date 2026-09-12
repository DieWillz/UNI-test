from __future__ import annotations

from uni.knowledge.base import CouncilResponse, KnowledgeBase


def test_short_exact_topic_can_be_found(tmp_path) -> None:
    kb = KnowledgeBase(tmp_path / "kb.sqlite")
    kb.store_response(CouncilResponse(
        response_id="r1",
        task_id="t1",
        provider="local",
        topic="bug fix",
        response_text="resolved regression safely",
        confidence=0.8,
        verified=True,
    ))

    found = kb.find_similar_responses("bug fix", limit=5)

    assert [item.response_id for item in found] == ["r1"]
