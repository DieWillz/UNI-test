"""Chat regressions. Camera/device/model transports are synthetic, never hardware."""
import asyncio
import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from uni.capabilities.camera import CameraCapability
from uni.config import Config
from uni.contracts import ToolResult
from uni.webui import server


@pytest.fixture
def handler(monkeypatch, tmp_path):
    h = object.__new__(server._Handler)
    h.responses = []
    h._json = lambda code, body: h.responses.append((code, body))
    h.agent = SimpleNamespace(capabilities={}, _init_error=None)
    h._get_chat_agent = lambda: h.agent
    h._xt_session = lambda agent: pytest.fail("Unrelated chat must not start a device session")
    monkeypatch.setattr(server, "_run_async", lambda coro, **kw: asyncio.run(coro))
    monkeypatch.setattr(server, "load_config", Config)
    monkeypatch.setattr(server, "_ROOT", tmp_path)
    return h


def test_camera_frame_uses_async_capture(handler, tmp_path):
    class Capture:
        def isOpened(self): return True
        def read(self): return True, np.full((8, 8, 3), 100, dtype=np.uint8)
    camera = CameraCapability(tmp_path)
    camera._capture = Capture()
    handler.agent.capabilities["camera"] = camera
    handler._handle_camera_frame()
    code, body = handler.responses[-1]
    assert code == 200, body
    raw = base64.b64decode(body["image_b64"].split(",", 1)[1])
    assert cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR).shape == (8, 8, 3)


def test_disabled_camera_does_not_open_hardware(handler, tmp_path):
    handler.agent.capabilities["camera"] = CameraCapability(tmp_path)
    handler._handle_camera_frame()
    assert handler.responses[-1][0] == 409


def test_camera_start_requires_explicit_notice(handler):
    handler._handle_camera_start({})
    assert handler.responses[-1][0] == 400


@pytest.mark.parametrize("image", [42, "data:image/svg+xml;base64,PHN2Zz4=", "not base64"])
def test_bad_image_rejected_before_agent_or_device(handler, image):
    handler._handle_chat({"text": "выставь мощность 25%", "image": image})
    assert handler.responses[-1][0] == 400


def test_explicit_power_uses_manual_transport_not_browser(handler):
    calls = []
    async def transport(name, args, source=server.MANUAL):
        calls.append((name, args, source))
        return ToolResult(success=True, data={"value": 25}, message="transport acknowledged")
    handler._run_xtoys_device_tool = transport
    handler._handle_chat({"text": "выставь мощность 25%"})
    assert calls == [("xtoys.set_intensity", {"value": 25}, server.MANUAL)]
    code, body = handler.responses[-1]
    assert code == 200
    assert body["status"] == "not_verified"
    assert body["transport_acknowledged"] is True
    assert body["outcome"]["actions"][0]["verified"] is False


@pytest.mark.parametrize("text", ["мощность 101%", "мощность -1%", "мощность 51%"])
def test_power_outside_config_limit_never_dispatches(handler, text):
    handler._handle_chat({"text": text})
    assert handler.responses[-1][0] == 400


def test_stop_file_blocks_chat_power(handler, tmp_path):
    (tmp_path / "STOP.txt").write_text("STOP")
    handler._handle_chat({"text": "мощность 25%"})
    assert handler.responses[-1][0] == 409


def test_image_only_is_analyzed_without_device_session(handler):
    async def vision(image, text):
        assert image.startswith("data:image/png;base64,")
        return "Синтетический серый квадрат"
    handler.agent.brain = SimpleNamespace(vision=vision)
    _, encoded = cv2.imencode(".png", np.full((8, 8, 3), 100, dtype=np.uint8))
    handler._handle_chat({"image": "data:image/png;base64," + base64.b64encode(encoded).decode()})
    code, body = handler.responses[-1]
    assert code == 200, body
    assert body["text"] == "Синтетический серый квадрат"
    assert body["status"] == "not_verified"


def test_chat_status_is_passive_and_does_not_claim_physical_observation(handler, monkeypatch):
    monkeypatch.setattr(server, "_INTIFACE", None)
    monkeypatch.setattr(server, "_TOY_COORDINATOR", None)
    monkeypatch.setattr(server, "_XT_SESSION", None)
    method = getattr(handler, "_handle_chat_status", None)
    assert callable(method), "Missing passive chat telemetry"
    method()
    code, body = handler.responses[-1]
    assert code == 200
    assert body["connected"] is False
    assert body["observed_value"] is None
    assert body["verification"] == "not_verified"


def test_web_voice_preference_is_request_local_and_does_not_mutate_config():
    from uni import event_loop
    gate = getattr(event_loop, "RESPONSE_SPEECH_ENABLED", None)
    assert gate is not None, "Web chat needs a task-local speech gate to avoid duplicate TTS"
    loop = object.__new__(event_loop.EventLoop)
    loop.config = Config()
    loop.config.agent.speak_responses = True
    async def check():
        token = gate.set(False)
        try:
            assert await loop._speak("Не озвучивать") is False
            assert loop.config.agent.speak_responses is True
        finally:
            gate.reset(token)
        assert gate.get() is True
    asyncio.run(check())


def test_chat_does_not_reuse_previous_task_outcome(handler):
    from uni.contracts import TaskOutcome
    from uni.event_loop import RESPONSE_SPEECH_ENABLED
    old = TaskOutcome.finalize(command="привет", message="Старый ответ")
    async def run_cycle(text):
        assert RESPONSE_SPEECH_ENABLED.get() is False
        return "Новый ответ"
    handler.agent.event_loop = SimpleNamespace(run_cycle=run_cycle, last_outcome=old)
    handler._handle_chat({"text": "привет", "use_voice": False})
    code, body = handler.responses[-1]
    assert code == 200
    assert body["task_id"] != old.task_id
    assert body["outcome"]["message"] == "Новый ответ"


def test_real_coordinator_manual_dispatch_and_emergency_latch(handler, monkeypatch):
    from uni.xtoys_control_coordinator import ToyControlCoordinator
    class Bridge:
        connected = True
        value = 0
        async def oscillate(self, value):
            self.value = value
            return {"ok": True}
        def status(self): return {"connected": True, "devices": ["Synthetic test device"], "value": self.value}
    bridge = Bridge()
    coordinator = ToyControlCoordinator(bridge)
    handler._toy_coordinator = lambda: coordinator
    monkeypatch.setattr(server, "_INTIFACE", bridge)
    handler._handle_chat({"text": "мощность 25%"})
    assert bridge.value == 25
    assert handler.responses[-1][1]["status"] == "not_verified"
    asyncio.run(coordinator.emergency_stop())
    handler._handle_chat({"text": "мощность 25%"})
    assert bridge.value == 0
    assert coordinator.emergency_stopped
    assert handler.responses[-1][0] == 409


@pytest.mark.parametrize("route", ["/api/camera/frame", "/api/camera/stop"])
def test_camera_post_consumes_body_before_next_keepalive_request(handler, monkeypatch, route):
    import http.client
    import json
    import threading
    from http.server import ThreadingHTTPServer
    class Handler(server._Handler):
        def log_message(self, *args): pass
        def _get_chat_agent(self): return handler.agent
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection(*httpd.server_address, timeout=3)
    try:
        conn.request("POST", route, body="{}", headers={"Content-Type": "application/json"})
        res = conn.getresponse(); res.read()
        conn.request("GET", "/api/chat/status")
        res = conn.getresponse()
        body = res.read()
        assert res.status == 200, body
        assert json.loads(body)["observed_value"] is None
    finally:
        conn.close(); httpd.shutdown(); httpd.server_close(); thread.join(timeout=3)


def test_webp_is_normalized_to_png_before_vlm():
    from uni.webui.chat_support import validated_image
    _, encoded = cv2.imencode(".webp", np.full((8, 8, 3), 100, np.uint8))
    image = validated_image("data:image/webp;base64," + base64.b64encode(encoded).decode())
    assert image.startswith("data:image/png;base64,")
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(image.split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (8, 8, 3)


def test_timed_polite_power_request_uses_bounded_hold_and_transport_ack(handler):
    calls = []

    class Queue:
        async def manual_hold(self, value, duration, *, speech=""):
            calls.append((value, duration, speech))
            return {"accepted": True, "transport_acknowledged": True, "current_value": value}

    handler.agent.control_queue = Queue()
    handler._handle_chat({"text": "а вы можете включить мощность 50% на 30 секунд?"})

    code, body = handler.responses[-1]
    assert code == 200
    assert calls and calls[0][0:2] == (50, 30.0)
    assert body["transport_acknowledged"] is True
    assert "50%" in body["text"] and "30" in body["text"]
