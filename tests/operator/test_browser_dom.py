"""Browser-only behavioral fixtures; never attach to a user's browser/profile."""
from __future__ import annotations

import asyncio

import pytest

from uni.browser_session import BrowserSession
from uni.operator.dom import StaleDOMRef
from browser_fixtures import local_browser


def target(snapshot, name):
    item = next(el for el in snapshot["elements"] if el["name"] == name)
    return {"ref": item["ref"], "snapshot_id": snapshot["snapshot_id"]}


@pytest.mark.asyncio
async def test_observation_never_starts_browser_or_empty_page(tmp_path):
    session = BrowserSession(user_data_dir=str(tmp_path / "not-created"))
    result = await session.operator_dom.inspect()
    assert result["errors"] == ["browser_not_running"]
    assert not (tmp_path / "not-created").exists()
    assert session._context is None


@pytest.mark.asyncio
async def test_bounded_inspect_prioritizes_controls_and_semantic_scope(local_browser):
    session, page = local_browser
    await page.set_content('<div role="region" aria-label="Settings">' +
                           '<span>noise</span>' * 300 +
                           '<button>Save</button></div><button>Outside</button>')
    snapshot = await session.operator_dom.inspect(limit=1)
    assert snapshot["elements"][0]["name"] == "Save"
    scoped = await session.operator_dom.inspect(scope={"role": "region", "name": "Settings"})
    assert "Save" in [el["name"] for el in scoped["elements"]]
    assert "Outside" not in [el["name"] for el in scoped["elements"]]
    found = await session.operator_dom.find(name="Save", role="button", limit=1)
    assert [el["name"] for el in found["elements"]] == ["Save"]
    assert found["snapshot_id"] != scoped["snapshot_id"]


@pytest.mark.asyncio
async def test_refs_reject_mutation_new_snapshot_and_navigation(local_browser):
    session, page = local_browser
    await page.set_content('<button>Save</button>')
    snapshot = await session.operator_dom.inspect()
    await page.evaluate("document.body.dataset.changed = 'yes'")
    with pytest.raises(StaleDOMRef):
        await session.operator_dom.act("click_ref", **target(snapshot, "Save"))
    snapshot = await session.operator_dom.inspect()
    await session.operator_dom.inspect()
    with pytest.raises(StaleDOMRef):
        await session.operator_dom.act("read", **target(snapshot, "Save"))
    snapshot = await session.operator_dom.inspect()
    await page.goto('data:text/html,<button>Other</button>')
    with pytest.raises(StaleDOMRef):
        await session.operator_dom.act("click_ref", **target(snapshot, "Save"))


@pytest.mark.asyncio
async def test_disabled_target_rejected_and_read_uncheck_are_real_observations(local_browser):
    session, page = local_browser
    await page.set_content('<input aria-label="Disabled" disabled value="original">'
                           '<input aria-label="Toggle" type="checkbox" checked>')
    snapshot = await session.operator_dom.inspect()
    with pytest.raises(ValueError, match="disabled_target"):
        await session.operator_dom.act("fill_ref", text="changed", **target(snapshot, "Disabled"))
    assert await page.get_by_label("Disabled").input_value() == "original"
    snapshot = await session.operator_dom.inspect()
    await session.operator_dom.act("uncheck_ref", **target(snapshot, "Toggle"))
    snapshot = await session.operator_dom.inspect()
    result = await session.operator_dom.act("read", **target(snapshot, "Toggle"))
    assert result["observed"]["checked"] is False
    assert result["status"] == "not_verified"


@pytest.mark.asyncio
async def test_tab_ids_stable_popup_invalidates_old_refs(local_browser):
    session, page = local_browser
    await page.set_content('<button>Original</button>')
    original_id = session.tab_id(page)
    snapshot = await session.operator_dom.inspect()
    async with page.expect_popup() as pending:
        await page.evaluate("window.open('about:blank')")
    popup = await pending.value
    assert session.tab_id(popup) != original_id
    assert session._operator_epoch != session.operator_dom._epoch
    with pytest.raises(StaleDOMRef):
        await session.operator_dom.act("click_ref", **target(snapshot, "Original"))
    await session.change_tab("close_tab", tab_id=session.tab_id(popup))
    assert session.tab_id(page) == original_id
    assert [item["tab_id"] for item in await session.list_tabs()] == [original_id]


@pytest.mark.asyncio
async def test_download_event_saves_new_file_and_existing_destination_survives(local_browser, tmp_path):
    session, page = local_browser
    await page.set_content('<a download="sample.txt" href="data:text/plain,fixture">Download</a>')
    path = tmp_path / "sample.txt"
    snapshot = await session.operator_dom.inspect()
    result = await session.operator_dom.act("download", path=str(path), **target(snapshot, "Download"))
    assert path.read_text() == "fixture"
    assert result["download_event"]["suggested_filename"] == "sample.txt"
    assert result["file_observation"]["size"] == 7
    assert result["status"] == "not_verified"
    snapshot = await session.operator_dom.inspect()
    with pytest.raises(FileExistsError):
        await session.operator_dom.act("download", path=str(path), **target(snapshot, "Download"))
    assert path.read_text() == "fixture"


@pytest.mark.asyncio
async def test_missing_download_event_leaves_no_fake_destination(local_browser, tmp_path):
    session, page = local_browser
    await page.set_content('<button>No download</button>')
    snapshot = await session.operator_dom.inspect()
    path = tmp_path / "not-a-download.txt"
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(session.operator_dom.act("download", path=str(path),
                             **target(snapshot, "No download")), timeout=0.5)
    assert not path.exists()


@pytest.mark.asyncio
async def test_upload_requires_file_and_reobserves_target_files(local_browser, tmp_path):
    session, page = local_browser
    await page.set_content('<input aria-label="Upload" type="file">')
    path = tmp_path / "fixture.txt"
    path.write_text("fixture", encoding="utf-8")
    snapshot = await session.operator_dom.inspect()
    result = await session.operator_dom.act("upload", paths=[str(path)], **target(snapshot, "Upload"))
    assert result["file_observation"]["files"][0]["name"] == "fixture.txt"
    assert result["file_observation"]["files"][0]["size"] == 7
    snapshot = await session.operator_dom.inspect()
    with pytest.raises(ValueError, match="upload_path_must_be_existing_absolute_file"):
        await session.operator_dom.act("upload", paths=[str(tmp_path / "missing.txt")],
                                      **target(snapshot, "Upload"))


@pytest.mark.asyncio
async def test_scoped_ref_capture_rejects_stale_container(local_browser):
    session, page = local_browser
    await page.set_content('<section aria-label="Scope"><button>Inside</button></section>'
                           '<button>Outside</button>')
    snapshot = await session.operator_dom.inspect()
    scoped = await session.operator_dom.inspect(scope=target(snapshot, "Scope"))
    assert [el["name"] for el in scoped["elements"]] == ["Inside", "Scope"]
    await page.evaluate("document.querySelector('section').dataset.changed='yes'")
    stale = await session.operator_dom.inspect(scope=target(scoped, "Scope"))
    assert stale["elements"] == []
    assert stale["errors"] == ["stale_ref"]


@pytest.mark.asyncio
async def test_viewport_scroll_works_without_elements_and_element_scroll_stays_local(local_browser):
    session, page = local_browser
    await page.set_content('<div style="height:3000px"></div>')
    snapshot = await session.operator_dom.inspect()
    assert snapshot["elements"] == []
    await session.operator_dom.act("scroll", snapshot_id=snapshot["snapshot_id"], delta_y=100)
    assert await page.evaluate("scrollY") == 100
    await page.set_content('<div role="region" aria-label="Scroller" style="height:100px;overflow:auto">'
                           '<div style="height:900px">Content</div></div>')
    await page.evaluate("window.scrollTo(0,0)")
    snapshot = await session.operator_dom.inspect()
    await session.operator_dom.act("scroll_element", delta_y=80, **target(snapshot, "Scroller"))
    assert await page.get_by_role("region").evaluate("el=>el.scrollTop") == 80
    assert await page.evaluate("scrollY") == 0


@pytest.mark.asyncio
async def test_hover_mutation_cannot_race_into_ref_click(local_browser):
    session, page = local_browser
    await page.set_content('<button onpointerover="this.dataset.changed=1" '
                           'onclick="window.clicked=true">Race target</button>')
    snapshot = await session.operator_dom.inspect()
    with pytest.raises(StaleDOMRef):
        await session.operator_dom.act("click_ref", **target(snapshot, "Race target"))
    assert await page.evaluate("window.clicked === true") is False
