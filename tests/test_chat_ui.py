"""Real WebUI DOM/scripts with isolated HTTP fixtures; no physical device access."""
import base64
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright, expect

WEBUI = Path(__file__).resolve().parents[1] / "uni" / "webui"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4S8AAAAASUVORK5CYII=")


@pytest.fixture
def ui(request):
    state = {"role": "reviewer", "calls": [], "role_error": False, "offline": False,
             "agent_ready": getattr(request, "param", True)}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context()
        context.route_web_socket("**/*", lambda ws: ws.close())
        page = context.new_page()
        page.set_default_timeout(3000)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def route(request):
            path = urlparse(request.request.url).path
            if urlparse(request.request.url).hostname == "uni.test" and not path.startswith("/api/"):
                file = WEBUI / (path.lstrip("/") or "index.html")
                if file.is_file() and file.resolve().is_relative_to(WEBUI):
                    return request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream")
            if request.request.method == "OPTIONS":
                return request.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "GET, POST"})
            body = request.request.post_data_json if request.request.post_data else None
            state["calls"].append((path, body))
            code, data = 200, {}
            if path == "/api/roles": data = {"roles": ["assistant", "reviewer"], "current": state["role"]}
            elif path == "/api/safety": data = {"agent_ready": state["agent_ready"]}
            elif path == "/api/role/switch":
                if state["role_error"]: code, data = 400, {"error": "роль не загружена"}
                else: state["role"] = body["role"]; data = {"ok": True, "role": state["role"]}
            elif path == "/api/chat/status":
                code, data = (503, {"error": "offline"}) if state["offline"] else (200, {"connected": True, "commanded_value": 25, "observed_value": None, "verification": "not_verified", "phase": "Тестовая фаза", "observed_at": 1})
            elif path == "/api/xtoys/session/status":
                code, data = (503, {"error": "offline"}) if state["offline"] else (200, {"intiface_connected": True, "device_connected": True, "current_intensity": 25, "verification": {"status": "not_verified"}, "phase": "Тестовая фаза", "status": "тестовый статус", "emergency_stop": False, "autonomous_running": False, "last_error": ""})
            elif path == "/api/chat": data = {"text": "Ответ тестового транспорта", "status": "not_verified"}
            elif path == "/api/camera/frame": data = {"ok": True, "image_b64": "data:image/png;base64," + base64.b64encode(PNG).decode()}
            elif path in ("/api/camera/start", "/api/camera/stop"): data = {"ok": True}
            elif path == "/api/tts": code, data = 503, {"error": "тестовый TTS недоступен"}
            elif path.endswith("/events"):
                event = {"type": "assistant_message", "source": "dorch", "text": "Тестовая реплика сессии", "ts": 1}
                return request.fulfill(content_type="text/event-stream", body="data: " + json.dumps(event) + "\n\n", headers={"Access-Control-Allow-Origin": "*"})
            request.fulfill(status=code, content_type="application/json", body=json.dumps(data), headers={"Access-Control-Allow-Origin": "*"})

        context.route("**/*", route)
        page.goto("http://uni.test/")
        page.locator('button.nav[data-page="chat"]').click()
        yield page, state, errors
        context.close()
        browser.close()


def test_current_role_and_apply_readback(ui):
    page, state, errors = ui
    expect(page.locator("#roleNow")).to_have_text("reviewer")
    expect(page.locator("#roleSel")).to_have_value("reviewer")
    page.locator("#roleSel").select_option("assistant")
    page.get_by_role("button", name="Применить роль", exact=True).click()
    expect(page.locator("#roleNow")).to_have_text("assistant")
    assert state["role"] == "assistant"
    assert not errors


def test_role_failure_keeps_confirmed_role(ui):
    page, state, _ = ui
    state["role_error"] = True
    page.locator("#roleSel").select_option("assistant")
    page.get_by_role("button", name="Применить роль", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("роль не загружена")
    expect(page.locator("#roleNow")).to_have_text("reviewer")


def test_image_upload_has_preview_and_reaches_chat(ui):
    page, state, errors = ui
    page.locator("#speakChk").uncheck()
    page.locator("#imgInput").set_input_files({"name": "test.png", "mimeType": "image/png", "buffer": PNG})
    expect(page.locator("#chatBox img")).to_be_visible()
    expect(page.locator("#chatBox")).to_contain_text("Ответ тестового транспорта")
    body = next(body for path, body in state["calls"] if path == "/api/chat")
    assert body["image"].startswith("data:image/png;base64,")
    assert body["use_voice"] is False
    assert not errors


def test_camera_is_explicit_preview_then_send_then_stop(ui):
    page, state, errors = ui
    assert not any(path == "/api/camera/start" for path, _ in state["calls"])
    page.locator("#camBtn").click()
    expect(page.locator("#chatCameraPreview")).to_be_visible()
    assert ("/api/camera/start", {"notice_ack": True}) in state["calls"]
    page.locator("#speakChk").uncheck()
    page.get_by_role("button", name="Отправить кадр", exact=True).click()
    expect(page.locator("#chatBox")).to_contain_text("Ответ тестового транспорта")
    page.locator("#camBtn").click()
    expect(page.locator("#chatCameraPanel")).to_be_hidden()
    assert any(path == "/api/camera/stop" for path, _ in state["calls"])
    assert not errors


def test_telemetry_never_displays_command_as_measured_motion(ui):
    page, state, _ = ui
    expect(page.locator("#dorchVal")).to_contain_text("25%")
    expect(page.locator("#chatDeviceStatus")).to_contain_text("не подтверждено")
    state["offline"] = True
    expect(page.locator("#dorchVal")).to_contain_text("нет данных", timeout=6000)


@pytest.mark.parametrize("ui", [False], indirect=True)
def test_telemetry_does_not_start_an_unready_agent(ui):
    page, state, errors = ui
    expect(page.locator("#dorchVal")).to_contain_text("Агент не запущен")
    assert any(path == "/api/safety" for path, _ in state["calls"])
    assert not any(path == "/api/xtoys/session/status" for path, _ in state["calls"])
    assert not errors


def test_tts_failure_is_visible_without_losing_text(ui):
    page, state, _ = ui
    page.locator("#chatIn").fill("привет")
    page.locator("#chatIn").press("Enter")
    expect(page.locator("#chatBox")).to_contain_text("Ответ тестового транспорта")
    expect(page.locator("#chatBox")).to_contain_text("TTS недоступен")


def test_session_speech_also_appears_as_text_without_replay_duplicates(ui):
    page, state, _ = ui
    expect(page.locator("#chatBox")).to_contain_text("Тестовая реплика сессии")
    expect(page.locator("#chatBox .msg").filter(has_text="Тестовая реплика сессии")).to_have_count(1)
    assert not any(path == "/api/tts" for path, _ in state["calls"])


def test_ordinary_chat_does_not_repeat_task_verification_warning(ui):
    page, state, _ = ui
    page.locator("#speakChk").uncheck()
    page.locator("#chatIn").fill("привет")
    page.locator("#chatIn").press("Enter")
    expect(page.locator("#chatBox")).to_contain_text("Ответ тестового транспорта")
    expect(page.locator("#chatBox")).not_to_contain_text("not_verified")
    expect(page.locator("#chatBox")).not_to_contain_text("Выполнение действия")
