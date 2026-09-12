from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from uni.config import Config


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(Config().model_dump(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_snapshot_exposes_major_groups_and_masks_secrets(tmp_path: Path) -> None:
    from uni.webui.config_admin import build_admin_config_snapshot

    path = tmp_path / "config.yaml"
    _write_config(path)
    snapshot = build_admin_config_snapshot(path)
    paths = {field["path"]: field for group in snapshot["groups"] for field in group["fields"]}

    for required in (
        "brain.model", "capabilities.speech.microphone_gain",
        "capabilities.vision.provider", "capabilities.vision.tier0_ocr_enabled",
        "autonomous.enabled", "capabilities.xtoys.max_intensity",
    ):
        assert required in paths

    assert paths["brain.api_key"]["secret"] is True
    assert paths["brain.api_key"]["value"] == ""
    assert paths["brain.api_key"]["secret_set"] is True
    assert paths["agent.verification_enabled"]["readonly"] is True
    assert "agent.autonomous.enabled" not in paths


def test_apply_updates_persists_validated_values(tmp_path: Path) -> None:
    from uni.webui.config_admin import apply_admin_config_updates

    path = tmp_path / "config.yaml"
    _write_config(path)
    result = apply_admin_config_updates(path, {
        "brain.temperature": 0.25,
        "capabilities.speech.microphone_gain": 7.5,
        "capabilities.vision.provider": "gradio",
        "capabilities.vision.tier0_ocr_enabled": False,
        "autonomous.enabled": True,
        "capabilities.xtoys.max_intensity": 55,
    })

    saved = Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert saved.brain.temperature == 0.25
    assert saved.capabilities.speech.microphone_gain == 7.5
    assert saved.capabilities.vision.provider == "gradio"
    assert saved.capabilities.vision.tier0_ocr_enabled is False
    assert saved.autonomous.enabled is True
    assert saved.capabilities.xtoys.max_intensity == 55
    assert set(result["changed"]) == {
        "brain.temperature",
        "capabilities.speech.microphone_gain",
        "capabilities.vision.provider",
        "capabilities.vision.tier0_ocr_enabled",
        "autonomous.enabled",
        "capabilities.xtoys.max_intensity",
    }


def test_protected_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    from uni.webui.config_admin import apply_admin_config_updates

    path = tmp_path / "config.yaml"
    _write_config(path)
    with pytest.raises(ValueError, match="read-only"):
        apply_admin_config_updates(path, {"agent.verification_enabled": False})
    with pytest.raises(ValueError, match="unknown config field"):
        apply_admin_config_updates(path, {"dangerous.arbitrary.path": True})


def test_invalid_update_does_not_modify_file(tmp_path: Path) -> None:
    from uni.webui.config_admin import apply_admin_config_updates

    path = tmp_path / "config.yaml"
    _write_config(path)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        apply_admin_config_updates(path, {"capabilities.speech.microphone_gain": 1000})
    assert path.read_bytes() == before


def test_secret_updates_are_write_only(tmp_path: Path) -> None:
    from uni.webui.config_admin import apply_admin_config_updates, build_admin_config_snapshot

    path = tmp_path / "config.yaml"
    _write_config(path)
    apply_admin_config_updates(path, {"brain.api_key": "new-secret"})
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["brain"]["api_key"] == "new-secret"

    snapshot = build_admin_config_snapshot(path)
    fields = {field["path"]: field for group in snapshot["groups"] for field in group["fields"]}
    assert fields["brain.api_key"]["value"] == ""
    assert fields["brain.api_key"]["secret_set"] is True


def test_admin_config_http_endpoint_exposes_schema() -> None:
    import json
    import socket
    import threading
    import urllib.request

    import uni.webui.server as srv

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd = srv.ThreadingHTTPServer(("127.0.0.1", port), srv._Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/admin/config", timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert any(group["title"] == "Зрение: OCR / Vision" for group in body["groups"])
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_admin_config_http_post_accepts_empty_update() -> None:
    import json
    import socket
    import threading
    import urllib.request

    import uni.webui.server as srv

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd = srv.ThreadingHTTPServer(("127.0.0.1", port), srv._Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/admin/config",
            data=json.dumps({"updates": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert response.status == 200
        assert body["ok"] is True and body["saved"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


def test_settings_page_uses_schema_driven_editor() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "uni" / "webui" / "index.html").read_text(encoding="utf-8")
    assert 'id="configSettingsGrid"' in html
    assert 'js/settings.js' in html
    assert 'css/settings.css' in html


def test_settings_editor_renders_and_saves_in_real_browser() -> None:
    import json
    import mimetypes
    from urllib.parse import urlparse

    from playwright.sync_api import sync_playwright, expect

    webui = Path(__file__).resolve().parents[1] / "uni" / "webui"
    state: dict[str, object] = {"updates": None}
    snapshot = {"version": 1, "config_path": "C:/LLM/UNI/config.yaml", "groups": [{
        "id": "0", "title": "Модель и LLM", "fields": [{
            "path": "brain.temperature", "label": "Температура", "kind": "number",
            "value": 0.85, "secret": False, "secret_set": False, "readonly": False,
            "restart_required": True, "step": 0.05,
        }],
    }]}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context()
        page = context.new_page()

        def route(req):
            parsed = urlparse(req.request.url)
            path = parsed.path
            if parsed.hostname == "uni.test" and not path.startswith("/api/"):
                file = webui / (path.lstrip("/") or "index.html")
                if file.is_file() and file.resolve().is_relative_to(webui):
                    return req.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or "application/octet-stream")
            body = req.request.post_data_json if req.request.post_data else None
            data: dict = {}
            if path == "/api/admin/config" and req.request.method == "GET":
                data = snapshot
            elif path == "/api/admin/config" and req.request.method == "POST":
                state["updates"] = (body or {}).get("updates")
                updated = json.loads(json.dumps(snapshot))
                updated["groups"][0]["fields"][0]["value"] = state["updates"]["brain.temperature"]
                data = {"ok": True, "saved": True, "changed": ["brain.temperature"],
                        "restart_required": ["brain.temperature"], "config": updated}
            elif path == "/api/roles":
                data = {"roles": ["uni"], "current": "uni"}
            elif path == "/api/tts/engines":
                data = {"engines": []}
            elif path == "/api/config":
                data = {}
            return req.fulfill(status=200, content_type="application/json", body=json.dumps(data))

        context.route("**/*", route)
        page.goto("http://uni.test/")
        page.locator('button.nav[data-page="settings"]').click()
        expect(page.locator("#configSettingsGrid")).to_contain_text("Модель и LLM")
        field = page.locator('[data-config-path="brain.temperature"]')
        expect(field).to_have_value("0.85")
        field.fill("0.25")
        page.locator("#configSaveBtn").click()
        expect(page.locator("#configSettingsStatus")).to_contain_text("Сохранено: 1")
        assert state["updates"] == {"brain.temperature": 0.25}
        context.close()
        browser.close()


def test_every_config_field_has_human_description_and_tts_voice_choices(tmp_path: Path) -> None:
    from uni.webui.config_admin import build_admin_config_snapshot

    path = tmp_path / "config.yaml"
    _write_config(path)
    snapshot = build_admin_config_snapshot(path)
    fields = {field["path"]: field for group in snapshot["groups"] for field in group["fields"]}

    assert all(str(field.get("description", "")).strip() for field in fields.values())
    assert fields["capabilities.speech.silero_speaker"]["kind"] == "select"
    assert {"xenia", "kseniya", "baya", "eugene", "aidar"}.issubset(
        set(fields["capabilities.speech.silero_speaker"]["options"])
    )
    assert fields["capabilities.speech.tts_voice"]["kind"] == "select"
    assert "ru_RU-irina-medium.onnx" in fields["capabilities.speech.tts_voice"]["options"]


def test_apply_updates_preserves_unmodelled_yaml_keys(tmp_path: Path) -> None:
    from uni.webui.config_admin import apply_admin_config_updates

    path = tmp_path / "config.yaml"
    _write_config(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["capabilities"]["vision"]["custom_runtime_hint"] = "keep-me"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")

    apply_admin_config_updates(path, {"brain.temperature": 0.35})
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["brain"]["temperature"] == 0.35
    assert saved["capabilities"]["vision"]["custom_runtime_hint"] == "keep-me"


def test_windows_replace_permission_error_falls_back_to_safe_write(tmp_path: Path, monkeypatch) -> None:
    import uni.webui.config_admin as admin

    path = tmp_path / "config.yaml"
    _write_config(path)
    real_replace = admin.os.replace

    def denied_replace(src, dst):
        if Path(dst) == path:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(admin.os, "replace", denied_replace)
    result = admin.apply_admin_config_updates(path, {"brain.temperature": 0.45})
    saved = Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert result["saved"] is True
    assert saved.brain.temperature == 0.45
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_descriptions_explain_effect_instead_of_repeating_label(tmp_path: Path) -> None:
    from uni.webui.config_admin import build_admin_config_snapshot

    path = tmp_path / "config.yaml"
    _write_config(path)
    snapshot = build_admin_config_snapshot(path)
    fields = {field["path"]: field for group in snapshot["groups"] for field in group["fields"]}
    descriptions = [str(field.get("description", "")) for field in fields.values()]
    assert all(not text.startswith("Изменяет «") for text in descriptions)
    auto = fields["autonomous.auto_start_session"]["description"].lower()
    assert "запуск" in auto and ("автомат" in auto or "сам" in auto)
    assert "команд" in auto or "сразу" in auto
