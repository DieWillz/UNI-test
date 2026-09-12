from __future__ import annotations

import pytest

from uni.operator.file_provider import FileProvider


@pytest.mark.asyncio
async def test_write_then_read_returns_fresh_file_observation(tmp_path) -> None:
    provider = FileProvider()
    path = tmp_path / "note.txt"

    written = await provider.act("write_text", path=str(path), text="UNI test")
    read = await provider.act("read", path=str(path))

    assert written["path"] == str(path.resolve())
    assert written["size"] > 0
    assert read["text"] == "UNI test"
    assert read["sha256"] == written["sha256"]


@pytest.mark.asyncio
async def test_write_does_not_create_missing_parent_implicitly(tmp_path) -> None:
    provider = FileProvider()
    path = tmp_path / "missing" / "note.txt"

    with pytest.raises(ValueError, match="parent_directory_missing"):
        await provider.act("write_text", path=str(path), text="x")


@pytest.mark.asyncio
async def test_exists_and_list_are_bounded(tmp_path) -> None:
    provider = FileProvider(max_list_entries=2)
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    listing = await provider.act("list", path=str(tmp_path))
    exists = await provider.act("exists", path=str(tmp_path / "a.txt"))

    assert len(listing["entries"]) == 2
    assert listing["truncated"] is True
    assert exists["exists"] is True


@pytest.mark.asyncio
async def test_delete_removes_only_explicit_path(tmp_path) -> None:
    provider = FileProvider()
    path = tmp_path / "remove.txt"
    other = tmp_path / "keep.txt"
    path.write_text("remove", encoding="utf-8")
    other.write_text("keep", encoding="utf-8")

    result = await provider.act("delete", path=str(path))

    assert result["removed"] is True
    assert not path.exists()
    assert other.exists()
