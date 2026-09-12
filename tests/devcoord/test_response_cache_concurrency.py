from __future__ import annotations

from uni.devcoord.aggregator import ResponseCache


def test_multiple_cache_instances_preserve_each_others_entries(tmp_path):
    first = ResponseCache(tmp_path)
    second = ResponseCache(tmp_path)

    first.set("task-1", "provider-a", "alpha")
    second.set("task-2", "provider-b", "beta")

    restored = ResponseCache(tmp_path)
    assert restored.get("task-1", "provider-a") == "alpha"
    assert restored.get("task-2", "provider-b") == "beta"

def test_cache_recovers_from_valid_non_object_json(tmp_path):
    cache_file = tmp_path / "responses.json"
    cache_file.write_text("[]", encoding="utf-8")

    cache = ResponseCache(tmp_path)
    assert cache.get("task", "provider") is None

    cache.set("task", "provider", "answer")
    restored = ResponseCache(tmp_path)
    assert restored.get("task", "provider") == "answer"
