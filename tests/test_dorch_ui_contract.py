from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "uni" / "webui"


def test_dorch_ui_has_no_per_action_physical_confirmation_control():
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    js = (WEBUI / "js" / "chat-controls.js").read_text(encoding="utf-8")
    assert 'id="dorchConfirm"' not in html
    assert "confirmDorchPhysical" not in js
    assert "/api/intiface/confirm-physical" not in js


def test_active_dorch_errors_do_not_require_verified_physical():
    server = (WEBUI / "server.py").read_text(encoding="utf-8")
    active_lines = [line for line in server.splitlines() if "verified_physical" in line and "DEPRECATED" not in line]
    assert not active_lines, "Dorch active flow still mentions verified_physical: " + repr(active_lines[:10])


def test_dorch_ui_distinguishes_intiface_and_device_presence():
    js = (WEBUI / "js" / "chat-controls.js").read_text(encoding="utf-8")
    assert "data.intiface_connected" in js
    assert "data.device_connected" in js
    assert "устройство не найдено" in js
