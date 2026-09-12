"""Focused admin UI acceptance tests from ADMIN_UI_NEXT_AGENT.md.

Uses the real static WebUI with intercepted HTTP fixtures. No UNI backend, LLM,
Dorch device, camera, microphone, or filesystem action is started.
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright, expect

WEBUI = Path(__file__).resolve().parents[1] / "uni" / "webui"


@pytest.fixture
def admin_ui():
    state = {"requests": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.route_web_socket("**/*", lambda ws: ws.close())
        page = context.new_page()
        page.set_default_timeout(3500)
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        def route(route):
            request = route.request
            parsed = urlparse(request.url)
            path = parsed.path
            state["requests"].append((request.method, request.url, request.post_data))
            if parsed.hostname == "uni.test" and not path.startswith("/api/"):
                file = WEBUI / (path.lstrip("/") or "index.html")
                if file.is_file() and file.resolve().is_relative_to(WEBUI):
                    return route.fulfill(
                        body=file.read_bytes(),
                        content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream",
                    )
            payload = {}
            if path == "/api/admin/stack":
                payload = {"webui": {"running": True, "pid": 101}, "llama": {"running": True, "pid": 202, "model": "fixture-model"}}
            elif path == "/api/admin/hw": payload = {"cpu": 0, "ram": 0, "gpu": {"vram_free": 0, "vram_used": 0, "utilization": 0}}
            elif path == "/api/admin/git": payload = {"branch": "fixture", "dirty": False}
            elif path == "/api/roles": payload = {"roles": ["assistant"], "current": "assistant"}
            elif path == "/api/tts/engines": payload = {"engines": []}
            elif path == "/api/admin/config": payload = {"groups": [{"title": "LLM", "fields": [{"path": "brain.temperature", "label": "Temperature", "kind": "number", "value": 0.85, "restart_required": True, "readonly": False, "secret": False}]}]}
            elif path == "/api/config": payload = {}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        context.route("**/*", route)
        page.goto("http://uni.test/")
        yield page, state, errors
        context.close()
        browser.close()


def test_opening_endpoint_catalog_never_sends_post(admin_ui):
    page, state, errors = admin_ui
    state["requests"].clear()
    page.locator('button.nav[data-page="plugins"]').click()
    page.wait_for_timeout(500)

    posts = [(method, url) for method, url, _ in state["requests"] if method == "POST"]
    assert posts == []
    expect(page.locator("#probeTbl")).to_contain_text("/api/admin/stack")
    assert not errors


def test_api_tester_rejects_invalid_json_before_network(admin_ui):
    page, state, errors = admin_ui
    page.locator('button.nav[data-page="tools"]').click()
    page.locator("#tMethod").select_option("POST")
    page.locator("#tPath").fill("/api/test-do-not-send")
    page.locator("#tBody").fill('{"broken":')
    state["requests"].clear()
    page.get_by_role("button", name="➤").last.click()

    expect(page.locator("#tOut")).to_contain_text("JSON")
    assert not any("/api/test-do-not-send" in url for _, url, _ in state["requests"])
    assert not errors


def test_remote_origin_does_not_probe_visitor_loopback(admin_ui):
    page, state, errors = admin_ui
    page.wait_for_timeout(1800)
    direct = [
        url for _, url, _ in state["requests"]
        if urlparse(url).hostname in {"127.0.0.1", "localhost"}
    ]
    assert direct == []
    assert not errors


def test_overview_uses_server_stack_remotely_and_preserves_zero(admin_ui):
    page, _, errors = admin_ui
    expect(page.locator("#ovStack")).to_contain_text("fixture-model")
    llm_card = page.locator("#ovStack .card").filter(has_text="LLM").first
    expect(llm_card).to_contain_text("Доступен")
    cpu_value = page.locator("#ovHw .kv").filter(has_text="CPU").locator("span")
    expect(cpu_value).to_have_text("0")
    assert not errors


def test_safe_navigation_search_hotkeys_and_tabs(admin_ui):
    page, state, errors = admin_ui
    pages = ["overview", "transfer", "browser", "chat", "participants", "workspace", "consensus", "docs", "stats", "computer", "vision", "auto", "memory", "settings", "actions", "plugins", "tools"]
    for name in pages:
        page.locator(f'button.nav[data-page="{name}"]').first.click()
        assert page.locator(f'section.page[data-page="{name}"]').evaluate("el => el.classList.contains('act')")
    page.locator('button.nav[data-page="transfer"]').click()
    page.locator('.page[data-page="transfer"] .tab[data-t="logs"]').click()
    assert page.locator('.page[data-page="transfer"] .pane[data-t="logs"]').evaluate("el => el.classList.contains('act')")
    assert page.locator('.dorch-tabs .tab[data-dt="manual"]').evaluate("el => el.classList.contains('act')")
    search = page.locator("#navSearch")
    search.fill("\u043b\u043e\u0433\u0438")
    expect(page.locator('button.nav[data-page="transfer"]')).to_be_visible()
    search.fill("\u043c\u043e\u0434\u0435\u043b\u044c")
    expect(page.locator('button.nav[data-page="settings"]')).to_be_visible()
    search.fill("\u0433\u043e\u043b\u043e\u0441")
    expect(page.locator('button.nav[data-page="settings"]')).to_be_visible()
    search.fill("zz-no-such-section")
    expect(page.locator("#navEmpty")).to_be_visible()
    search.fill("")
    expect(page.locator("#navEmpty")).to_be_hidden()
    page.keyboard.press("Control+K")
    assert page.evaluate("document.activeElement && document.activeElement.id") == "navSearch"
    search.fill("\u043c\u043e\u0434\u0435\u043b\u044c")
    search.press("Enter")
    assert page.locator('section.page[data-page="settings"]').evaluate("el => el.classList.contains('act')")
    assert not any(method == "POST" and "/api/admin/actions" in url for method, url, _ in state["requests"])
    assert not errors


def test_mobile_menu_closes_and_page_has_no_horizontal_scroll(admin_ui):
    page, _, errors = admin_ui
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.locator("#sidebar").evaluate("el => getComputedStyle(el).visibility") == "hidden"
    page.locator("#burger").click()
    assert page.locator("#sidebar").evaluate("el => getComputedStyle(el).visibility") == "visible"
    expect(page.locator("#navBackdrop")).to_be_visible()
    page.locator('button.nav[data-page="settings"]').click()
    assert not page.evaluate("document.body.classList.contains('sb')")
    expect(page.locator("#navBackdrop")).to_be_hidden()
    page.locator("#burger").click()
    page.locator("#navBackdrop").click(position={"x": 380, "y": 400})
    assert page.evaluate("document.activeElement && document.activeElement.id") == "burger"
    assert page.locator("#sidebar").evaluate("el => getComputedStyle(el).visibility") == "hidden"
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert not errors


def test_responsive_safe_pages_and_125_percent_zoom(admin_ui):
    page, _, errors = admin_ui
    safe_pages = ["overview", "transfer", "browser", "chat", "participants", "workspace", "consensus", "docs", "stats", "computer", "vision", "auto", "memory", "settings", "actions", "plugins", "tools"]
    for width, height in [(1440, 900), (1024, 768), (390, 844)]:
        page.set_viewport_size({"width": width, "height": height})
        for name in safe_pages:
            page.evaluate("name => go(name)", name)
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 1, f"horizontal overflow {overflow}px on {name} at {width}x{height}"
    page.set_viewport_size({"width": 1024, "height": 768})
    page.evaluate("document.documentElement.style.zoom='1.25'")
    for name in ["overview", "settings", "chat", "tools", "plugins", "actions"]:
        page.evaluate("name => go(name)", name)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, f"horizontal overflow {overflow}px on {name} at 125% zoom"
    assert not errors


def test_unsaved_config_input_survives_navigation(admin_ui):
    page, _, errors = admin_ui
    page.locator('button.nav[data-page="settings"]').click()
    field = page.locator('[data-config-path="brain.temperature"]')
    expect(field).to_have_value("0.85")
    field.fill("0.42")
    page.locator('button.nav[data-page="overview"]').click()
    page.locator('button.nav[data-page="settings"]').click()
    expect(field).to_have_value("0.42")
    expect(page.locator('.config-badge.restart')).to_have_count(1)
    assert not errors


def test_runtime_overview_exposes_degraded_backend_status(admin_ui):
    page, state, errors = admin_ui

    def degraded(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "status": "degraded",
                "app": {
                    "chat": {"agent_ready": True},
                    "autonomous": {"enabled": True, "running": False},
                    "voice": {"listening": False},
                    "workspace": {"available": False},
                },
            }),
        )

    page.route("**/api/app", degraded)
    page.evaluate("window.loadRuntimeOverview()")
    expect(page.locator("#runtimeOverviewStatus")).to_have_text("DEGRADED")
    expect(page.locator("#runtimeOverviewStatus")).to_have_class("tag amb")
    assert not errors


def test_navigation_search_lives_in_topbar_not_sidebar() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    sidebar = html.split('<aside id="sidebar">', 1)[1].split('</aside>', 1)[0]
    topbar = html.split('<header id="topbar">', 1)[1].split('</header>', 1)[0]
    assert 'id="navSearch"' not in sidebar
    assert 'id="navSearch"' in topbar


def test_settings_groups_are_collapsible_and_apply_bar_exists() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    script = (WEBUI / "js" / "settings.js").read_text(encoding="utf-8")
    assert 'id="configApplyBar"' in html
    assert "<details class=\"config-group card\"" in script
    assert "Сохранить и применить" in html or "Сохранить и применить" in script
