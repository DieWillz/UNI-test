"""Offline real Chromium acceptance: DOM input + fresh independent observations."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from browser_fixtures import local_browser
from uni.contracts import VerificationStatus
from uni.operator.browser_provider import BrowserProvider, TargetNotFound
from uni.operator.models import PlanStep, Postcondition, TargetSpec
from uni.operator.verifier import PostconditionVerifier


@pytest.fixture
def playground():
    content = (Path(__file__).parent / "browser" / "playground.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (b"UNI download fixture" if self.path == "/download" else
                    b"<title>Second page</title><h1>Second page</h1>" if self.path == "/second" else content)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream" if self.path == "/download" else "text/html; charset=utf-8")
            if self.path == "/download":
                self.send_header("Content-Disposition", 'attachment; filename="example.txt"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


async def perform(provider, action, *, target=None, params=None, kind=None, expected=None):
    step = PlanStep(id="local", action=f"operator.browser.{action}", target=target,
                    params=params or {}, postcondition=Postcondition(kind=kind, params=expected or {}))
    await provider.act(action, target=target, **step.params)
    scene = await provider.inspect()
    decision = await PostconditionVerifier().verify(step, scene=scene)
    assert decision.status is VerificationStatus.VERIFIED, decision.reason
    assert decision.evidence
    return scene


@pytest.mark.asyncio
async def test_local_form_read_after_write_checkbox_select_and_save(local_browser, playground):
    session, page = local_browser
    await page.goto(playground)
    provider = BrowserProvider(session)
    await perform(provider, "fill", target=TargetSpec(role="textbox", name="Name"),
                  params={"text": "UNI test"}, kind="element.value_equals", expected={"value": "UNI test"})
    await perform(provider, "check", target=TargetSpec(role="checkbox", name="Enabled"),
                  kind="element.checked_equals", expected={"value": True})
    await perform(provider, "select", target=TargetSpec(role="combobox", name="Platform"),
                  params={"value": "Windows"}, kind="element.value_equals", expected={"value": "Windows"})
    await perform(provider, "click", target=TargetSpec(role="button", name="Save", exact=True),
                  kind="element.text_equals", expected={"target": {"role": "status", "text": "Saved", "exact": True}, "value": "Saved"})
    assert await page.get_by_label("Name", exact=True).input_value() == "UNI test"


@pytest.mark.asyncio
async def test_local_download_event_and_independent_stat(local_browser, playground, tmp_path):
    session, page = local_browser
    await page.goto(playground)
    provider = BrowserProvider(session)
    path = str(tmp_path / "download.txt")
    await perform(provider, "download", target=TargetSpec(role="link", name="Download", exact=True),
                  params={"path": path}, kind="browser.download_completed", expected={"path": path})
    assert Path(path).read_text() == "UNI download fixture"


@pytest.mark.asyncio
async def test_local_popup_switch_and_close_preserves_original_tab(local_browser, playground):
    session, page = local_browser
    await page.goto(playground)
    provider = BrowserProvider(session)
    before = session.tab_id(page)
    async with page.expect_popup():
        await provider.act("click", target=TargetSpec(role="link", name="New page", exact=True))
    scene = await provider.inspect()
    popup = next(tab["tab_id"] for tab in scene.browser["tabs"] if tab["tab_id"] != before)
    step = PlanStep(id="popup", action="operator.browser.click", postcondition=Postcondition(
        kind="browser.tab_appeared", params={"tab_id": popup}))
    decision = await PostconditionVerifier().verify(step, scene=scene)
    assert decision.status is VerificationStatus.VERIFIED, decision.reason
    await perform(provider, "switch_tab", params={"tab_id": popup}, kind="browser.title_contains",
                  expected={"text": "Second page"})
    await perform(provider, "close_tab", params={"tab_id": popup}, kind="browser.tab_disappeared",
                  expected={"tab_id": popup})
    assert (await provider.inspect()).browser["tab_id"] == before


@pytest.mark.asyncio
async def test_local_target_missing_scroll_is_bounded_and_recovers(local_browser, playground):
    session, page = local_browser
    await page.goto(playground)
    provider = BrowserProvider(session)
    await provider.act("click", target=TargetSpec(role="button", name="Bottom target"), scroll_budget=2)
    assert await page.evaluate("scrollY") > 0
    with pytest.raises(TargetNotFound):
        await provider.act("click", target=TargetSpec(role="button", name="Does not exist"), scroll_budget=2)
