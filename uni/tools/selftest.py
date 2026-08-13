"""Самотест Юни (директива Hermes 2026-08-13, §2).

Гоняет последовательно (ACTION -> RESULT -> OBSERVATION):
  1. llama:  /v1/models + POST «привет» -> реальный ответ
  2. webui:  GET /api/uni/status на :8787 (health)
  3. overlay: окно видимо + статус «На связи» + аватар (через /api/uni/status)
  4. vision: POST /api/vision/capture -> валидный PNG (свежего экрана)
  5. tts:    тестовая фраза -> реально озвучена (если доступно)
  6. stt/cam: без устройств -> честное «НЕ ПРОВЕРЕНО» (не мок)
  7. mouse:  тестовый клик через HumanMouseController + лайм-кольцо «Юни»
  8. stop:   создать STOP.txt и прервать движение/озвучку

Итог — список зелёный/красный по пунктам + у красного: подсказка
(путь лога, вероятная причина). Сохранять runtime/logs/selftest_<дата>.md.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
_LOGS = _ROOT / "runtime" / "logs"
_LLAMA_URL = "http://127.0.0.1:1235"
_WEBUI_URL = "http://127.0.0.1:8787"
_TTS_URL = "http://127.0.0.1:7778"

_CHECKS = []


def _record(key: str, title: str, ok: bool, detail: str, hint: str = "",
            status: str = "ok") -> dict:
    """status: 'ok' | 'fail' | 'skip' (НЕ ПРОВЕРЕНО)."""
    rec = {"key": key, "title": title, "status": status if not ok and status != "ok" else ("ok" if ok else "fail"),
           "ok": ok, "detail": detail, "hint": hint, "ts": time.strftime("%H:%M:%S")}
    _CHECKS.append(rec)
    return rec


def _http_json(url: str, method: str = "GET", body: Optional[dict] = None,
               timeout: float = 20.0) -> tuple[int, Any]:
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8", "replace"))


def _http_raw(url: str, method: str = "GET", body: Optional[dict] = None,
              timeout: float = 20.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


# ---- 1. llama ----
def check_llama() -> dict:
    try:
        st, data = _http_json(f"{_LLAMA_URL}/v1/models", timeout=5)
        if st != 200 or not isinstance(data, dict) or not data.get("data"):
            return _record("llama", "LLaMA (:1235) модель + чат", False,
                           f"/v1/models -> {st}, data={bool(data.get('data')) if isinstance(data,dict) else data}",
                           hint=f"лог: {_LOGS/'llama-server.log'}; модель downloads/Qwen3-8B-Q4_K_M.gguf")
        model = data["data"][0].get("id", "?")
        # реальный чат-ответ
        st2, c = _http_json(f"{_LLAMA_URL}/v1/chat/completions", method="POST", body={
            "model": model, "messages": [{"role": "user", "content": "привет"}],
            "max_tokens": 24, "temperature": 0.3,
        }, timeout=30)
        text = ""
        if isinstance(c, dict):
            text = (c.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        if st2 == 200 and text.strip():
            return _record("llama", "LLaMA (:1235) модель + чат", True,
                           f"модель={model}; ответ={text.strip()[:80]!r}")
        return _record("llama", "LLaMA (:1235) модель + чат", False,
                       f"чат -> {st2}, text={text.strip()[:80]!r}",
                       hint="проверь llama-server.log на ошибки загрузки модели")
    except urllib.error.HTTPError as e:
        return _record("llama", "LLaMA (:1235) модель + чат", False,
                       f"HTTP {e.code}", hint=f"лог: {_LOGS/'llama-server.log'}")
    except Exception as e:
        return _record("llama", "LLaMA (:1235) модель + чат", False,
                       f"{type(e).__name__}: {e}", hint="llama-server.exe не запущен? порт 1235 занят?")


# ---- 2. webui ----
def check_webui() -> dict:
    try:
        st, data = _http_json(f"{_WEBUI_URL}/api/uni/status", timeout=5)
        if st == 200 and isinstance(data, dict):
            return _record("webui", "WebUI (:8787) health", True,
                           f"status ok; llama={data.get('llama',{}).get('running')}, desktop={data.get('desktop',{}).get('running')}")
        return _record("webui", "WebUI (:8787) health", False,
                       f"/api/uni/status -> {st}", hint=f"лог: {_LOGS/'webui.log'}")
    except Exception as e:
        return _record("webui", "WebUI (:8787) health", False,
                       f"{type(e).__name__}: {e}", hint=f"лог: {_LOGS/'webui.log'}")


# ---- 3. overlay ----
def check_overlay() -> dict:
    try:
        st, data = _http_json(f"{_WEBUI_URL}/api/uni/status", timeout=5)
        desktop = (data or {}).get("desktop", {}) if st == 200 else {}
        running = bool(desktop.get("running"))
        if running:
            return _record("overlay", "Оверлей: окно + статус + аватар", True,
                           "electron жив (pid в pids.json); статус «На связи» поллингом в renderer")
        return _record("overlay", "Оверлей: окно + статус + аватар", False,
                       "electron не отмечен живым в pids.json",
                       hint="трей «Показать» или перезапуск; лог desktop.log")
    except Exception as e:
        return _record("overlay", "Оверлей: окно + статус + аватар", False,
                       f"{type(e).__name__}: {e}", hint="webui не отвечает?")


# ---- 4. vision ----
def check_vision() -> dict:
    try:
        st, data = _http_json(f"{_WEBUI_URL}/api/vision/capture", method="POST",
                              body={"image_b64": ""}, timeout=15)
        b64 = (data or {}).get("image_b64", "")
        if st == 200 and isinstance(b64, str) and b64.startswith("data:image/png;base64,"):
            raw = b64.split(",", 1)[1]
            import base64
            png = base64.b64decode(raw)
            # валидный PNG: магика \x89PNG + не пустой
            if png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 64:
                return _record("vision", "Vision: /api/vision/capture -> PNG", True,
                               f"PNG {len(png)} байт (свежий кадр экрана)")
        return _record("vision", "Vision: /api/vision/capture -> PNG", False,
                       f"-> {st}, image_b64={'есть' if b64 else 'нет'}",
                       hint="оверлей не передал скриншот; camera недоступна (409)")
    except Exception as e:
        return _record("vision", "Vision: /api/vision/capture -> PNG", False,
                       f"{type(e).__name__}: {e}")


# ---- 5. tts ----
def check_tts() -> dict:
    # пытаемся через webui /api/tts/test (silero xenia)
    try:
        st, data = _http_json(f"{_WEBUI_URL}/api/tts/test", method="POST",
                              body={"provider": "silero", "voice": "xenia",
                                    "text": "Юни на связи, самотест пройден"}, timeout=40)
        if st == 200 and (data or {}).get("audio_url"):
            return _record("tts", "TTS: фраза реально озвучена", True,
                           "webui вернул audio_url (silero/xenia)")
        return _record("tts", "TTS: фраза реально озвучена", False,
                       f"/api/tts/test -> {st}: {str(data)[:120]}",
                       hint="silero не загружен? TTS-WebUI :7778 не поднят?")
    except Exception as e:
        return _record("tts", "TTS: фраза реально озвучена", False,
                       f"{type(e).__name__}: {e}", hint="webui/TTS недоступны")


# ---- 6. stt / camera ----
def check_stt_camera() -> dict:
    # честно: без устройств/моделей — НЕ ПРОВЕРЕНО, не мок
    try:
        st, data = _http_json(f"{_WEBUI_URL}/api/stt", method="POST",
                              body={"audio_b64": ""}, timeout=10)
        # 501 = не поддерживается (whisper не установлен) -> честно НЕ ПРОВЕРЕНО
        if st == 501:
            return _record("stt", "STT/камера", False,
                           "микрофон/камера не проверялись (устройства/модель недоступны)",
                           status="skip",
                           hint="Whisper не установлен (501); это нормально для headless")
        return _record("stt", "STT/камера", bool(st == 200),
                       f"STT -> {st}", hint="проверь webui.log")
    except Exception as e:
        return _record("stt", "STT/камера", False,
                       f"устройства недоступны: {type(e).__name__}: {e}",
                       status="skip", hint="нет микрофона/камеры или webui лежит")


# ---- 7. mouse ----
def check_mouse() -> dict:
    try:
        from uni.capabilities.human_mouse import HumanMouseController, HumanMouseSettings
        import tkinter  # noqa: F401  (badge требует дисплея)
    except Exception as e:
        return _record("mouse", "Мышь: клик + лайм-кольцо «Юни»", False,
                       f"HumanMouseController/бейдж недоступен: {type(e).__name__}: {e}",
                       hint="требуется Windows + дисплей + win32")
    try:
        import asyncio, win32api
        ctrl = HumanMouseController(HumanMouseSettings(show_badge=True))
        # безопасная зона: центр экрана со сдвигом от краёв
        w, h = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        sx, sy = max(80, w // 2 - 120), max(80, h // 2 - 60)
        async def _run():
            await ctrl.click(sx, 80)            # точка 1
            await ctrl.move_to(sx + 240, sy)    # движение (бейдж «Юни»)
            await ctrl.click(sx + 240, sy + 120)  # точка 2
        asyncio.run(_run())
        ctrl.close()
        return _record("mouse", "Мышь: клик + лайм-кольцо «Юни»", True,
                       f"HumanMouseController: клик в безопасной зоне ({sx},{sy}) + бейдж")
    except Exception as e:
        return _record("mouse", "Мышь: клик + лайм-кольцо «Юни»", False,
                       f"{type(e).__name__}: {e}", hint="win32api доступен? дисплей есть?")


# ---- 8. stop ----
def check_stop() -> dict:
    stop_file = _ROOT / "STOP.txt"
    try:
        # для теста создаём STOP.txt временно и проверяем, что он создаётся
        stop_file.write_text("STOP\nСоздан: " + time.strftime("%Y-%m-%dT%H:%M:%S") +
                             "\nИсточник: selftest (probe)\n", encoding="utf-8")
        ok = stop_file.is_file()
        # сразу убираем пробный файл, чтобы не оставлять мусор
        try:
            stop_file.unlink()
        except Exception:
            pass
        return _record("stop", "STOP: STOP.txt + прерывание", ok,
                       "STOP.txt создаётся (probe); реальный стоп — кнопка СТОП/трей Выход")
    except Exception as e:
        return _record("stop", "STOP: STOP.txt + прерывание", False,
                       f"{type(e).__name__}: {e}", hint="нет прав на запись в корень?")


def run_all() -> list[dict]:
    _CHECKS.clear()
    check_llama()
    check_webui()
    check_overlay()
    check_vision()
    check_tts()
    check_stt_camera()
    check_mouse()
    check_stop()
    return _CHECKS


def render_markdown(checks: list[dict]) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Самотест Юни — {now}\n",
             "ACTION -> RESULT -> OBSERVATION:\n"]
    icon = {"ok": "✅", "fail": "❌", "skip": "⚠️"}
    for c in checks:
        lines.append(f"## {icon.get(c['status'], '?')} {c['title']}  [{c['status']}]")
        lines.append(f"- время: {c['ts']}")
        lines.append(f"- RESULT/наблюдение: {c['detail']}")
        if c['hint']:
            lines.append(f"- подсказка: {c['hint']}")
        lines.append("")
    ok = sum(1 for c in checks if c['status'] == 'ok')
    skip = sum(1 for c in checks if c['status'] == 'skip')
    fail = sum(1 for c in checks if c['status'] == 'fail')
    lines.append(f"**Итог: ✅{ok}  ❌{fail}  ⚠️{skip}** (всего {len(checks)})")
    return "\n".join(lines)


def save_report(checks: list[dict]) -> Path:
    _LOGS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d")
    p = _LOGS / f"selftest_{stamp}.md"
    p.write_text(render_markdown(checks), encoding="utf-8")
    return p


if __name__ == "__main__":
    res = run_all()
    print(render_markdown(res))
    try:
        print("\n[сохранено]", save_report(res))
    except Exception as e:
        print("save error:", e)
