"""UNI WebUI — local-first development console for the AI Council.

Zero-dependency HTTP server (stdlib only) serving a single-page frontend and a
Server-Sent Events (SSE) stream that drives a REAL consensus round via
``uni.council.CouncilRound``. Browser participants need a live browser session; the
server honours CouncilConfig (browser_enabled, free_tier_only, inform_tos, min_interval)
exactly like the CLI (uni.council.run).

Run:
    py -3.12 -m uni.webui            # serves http://localhost:8787
    py -3.12 -m uni --webui          # same, from the main entrypoint

The SSE endpoint POST /api/round/start accepts JSON {topic, brief, files, tasks, only}
and streams progress events as they happen.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import queue
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from uni.config import load_config
from uni.council.participants import load_participants
from uni.council.round import CouncilRound
from uni.autonomous_session import AutonomousSession
from uni.contracts import ToolResult
from uni.intiface_bridge import IntifaceBridge
from uni.xtoys_patterns import XToysPatternEngine, PATTERN_NAMES
from uni.webui.ui_contract import (
    validate_ui_events, validate_component, resolve_action, CANON_COMPONENTS,
)
from uni.xtoys_control_coordinator import ToyControlCoordinator, MANUAL, MOTION, REMOTE, PATTERN, AUTONOMOUS
from uni.xtoys_motion import MotionToyController, MotionSettings

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]

# 🤖 Универсальный UI-движок (Директива Hermes: универсальный UI-движок Юни).
# In-memory хранилище ui_events по task_id / mission_id. В реальном агенте сюда
# пишет оркестратор; здесь _handle_chat оборачивает ответ LLM в generic-события,
# а поллинг-эндпоинты отдают их. НЕ удалять — это часть контракта backend→frontend.
_UI_TASKS: dict[str, list[dict]] = {}
_UI_MISSIONS: dict[str, list[dict]] = {}
_FRONTEND = _HERE / "index.html"

# ===== XToys autonomous session (device timeline + synced speech) =====
# Runs in its own background thread + asyncio loop so the HTTP handler stays sync.
_XT_SESSION: AutonomousSession | None = None
_XT_LOOP: asyncio.AbstractEventLoop | None = None
_XT_THREAD: Any = None

# 🤖 DC-03: очередь событий для оверлея Desktop Companion
_desktop_event_queue: "queue.Queue" = queue.Queue()


def _consent_path():
    return (_ROOT / "uni" / "memory" / "consent_log.jsonl")


def _read_consent():
    """Текущее согласие на наблюдение (DC-04)."""
    p = _consent_path()
    if not p.is_file():
        return {"observation_enabled": False, "level": "off", "last_change": None}
    try:
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return {"observation_enabled": False, "level": "off", "last_change": None}
        last = json.loads(lines[-1])
        return {
            "observation_enabled": bool(last.get("observation_enabled", False)),
            "level": last.get("level", "off"),
            "last_change": last.get("ts"),
        }
    except (OSError, json.JSONDecodeError):
        return {"observation_enabled": False, "level": "off", "last_change": None}


def _write_consent(observation_enabled: bool, level: str):
    """Сохраняет запись согласия в журнал (DC-04)."""
    p = _consent_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    level = level if level in ("off", "observe", "suggest", "act") else "off"
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "observation_enabled": bool(observation_enabled),
        "level": level,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # уведомляем оверлеи об изменении
    _desktop_event_queue.put({"type": "consent_changed", "consent": rec})
    return rec

# ===== Intiface (Buttplug) direct bridge =====
_INTIFACE: IntifaceBridge | None = None

# ===== Dorch neutral motion profiles =====
_XTOYS_PATTERN: XToysPatternEngine | None = None

# ===== ToyControlCoordinator: единый шлюз управления устройством =====
_TOY_COORDINATOR: ToyControlCoordinator | None = None
_MOTION: MotionToyController | None = None
_REMOTE_TIMER: threading.Timer | None = None
_REMOTE_ROOM_LOCK = threading.RLock()
_REMOTE_ROOM_EVENTS: list[dict[str, Any]] = []
_REMOTE_ROOM_NEXT_ID = 1
_REMOTE_GATEWAY = None
_REMOTE_GATEWAY_THREAD = None
_PUBLIC_TUNNEL_PROCESS: subprocess.Popen | None = None
_PUBLIC_TUNNEL_URL = ""


def _ensure_remote_gateway() -> None:
    global _REMOTE_GATEWAY, _REMOTE_GATEWAY_THREAD
    if _REMOTE_GATEWAY is not None:
        return
    _REMOTE_GATEWAY = ThreadingHTTPServer(("127.0.0.1", 8788), _RemoteGatewayHandler)
    _REMOTE_GATEWAY_THREAD = threading.Thread(target=_REMOTE_GATEWAY.serve_forever, daemon=True, name="uni-remote-gateway")
    _REMOTE_GATEWAY_THREAD.start()


def _start_public_tunnel() -> str:
    global _PUBLIC_TUNNEL_PROCESS, _PUBLIC_TUNNEL_URL
    # 🤖 B-06: env-флаг UNI_REMOTE_PUBLIC_BASE — использовать заданный публичный
    # base URL вместо cloudflared (аддитивно, без лома старого пути). Полезно,
    # когда публичный адрес уже есть (свой домен / frp / ngrok / reverse-proxy).
    env_base = os.environ.get("UNI_REMOTE_PUBLIC_BASE", "").strip().rstrip("/")
    if env_base:
        _PUBLIC_TUNNEL_URL = env_base
        _PUBLIC_TUNNEL_PROCESS = None
        return _PUBLIC_TUNNEL_URL
    if _PUBLIC_TUNNEL_PROCESS is not None and _PUBLIC_TUNNEL_PROCESS.poll() is None and _PUBLIC_TUNNEL_URL:
        return _PUBLIC_TUNNEL_URL
    _ensure_remote_gateway()
    binary = _HERE / "bin" / "cloudflared.exe"
    if not binary.is_file():
        raise RuntimeError("cloudflared.exe не установлен")
    process = subprocess.Popen(
        [str(binary), "tunnel", "--url", "http://127.0.0.1:8788", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _PUBLIC_TUNNEL_PROCESS = process
    _PUBLIC_TUNNEL_URL = ""
    lines: queue.Queue[str] = queue.Queue()
    def _read_output() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            lines.put(line)
    threading.Thread(target=_read_output, daemon=True, name="uni-cloudflared-log").start()
    deadline = time.time() + 25.0
    while time.time() < deadline and process.poll() is None:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            continue
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if match:
            _PUBLIC_TUNNEL_URL = match.group(0)
            return _PUBLIC_TUNNEL_URL
    if process.poll() is None:
        process.terminate()
    _PUBLIC_TUNNEL_PROCESS = None
    raise RuntimeError("cloudflared не выдал публичный адрес")


def _stop_public_tunnel() -> None:
    global _PUBLIC_TUNNEL_PROCESS, _PUBLIC_TUNNEL_URL
    process = _PUBLIC_TUNNEL_PROCESS
    _PUBLIC_TUNNEL_PROCESS = None
    _PUBLIC_TUNNEL_URL = ""
    if process is not None and process.poll() is None:
        process.terminate()


def _remote_timeout_stop() -> None:
    """Fail closed when a remote controller stops sending heartbeats."""
    global _TOY_COORDINATOR
    coordinator = _TOY_COORDINATOR
    if coordinator is None:
        return
    session = coordinator.remote_session
    if session is not None:
        session.connected = False
    loop = getattr(coordinator, "_loop", None)
    if loop is not None and not loop.is_closed():
        asyncio.run_coroutine_threadsafe(coordinator.release(REMOTE), loop)


def _safe_project_path(rel: str) -> Path:
    """Зарезервировано для будущей секции «Файлы проекта» в панели.

    Возвращает абсолютный путь внутри _ROOT, блокируя выход за пределы
    проекта (path-traversal, как ../). Паттерн адаптирован из сервера
    моста (server.js: safePath). Пока не используется фронтендом.
    """
    rel = (rel or "").replace("\\", "/").lstrip("/")
    full = (_ROOT / rel).resolve()
    if full != _ROOT and _ROOT not in full.parents:
        raise PermissionError(f"path escape blocked: {rel!r}")
    return full


# ===== Самотест / Демо-мышь / Скриншот оверлея (Hermes 2026-08-13) =====
def _selftest_last() -> dict:
    """Перенесено в routers_desktop (Q-08)."""
    from .routers_desktop import selftest_last as _f
    return _f()


def _mouse_demo() -> dict:
    """Перенесено в routers_desktop (Q-08)."""
    from .routers_desktop import mouse_demo as _f
    return _f()


def _overlay_capture() -> dict:
    """Перенесено в routers_desktop (Q-08)."""
    from .routers_desktop import overlay_capture as _f
    return _f()

# Один Agent на процесс сервера; собирается лениво при первом чат-запросе.
_CHAT_AGENT = None
_CHAT_FEED = None  # uni.context.feed_injector.ContextFeedInjector (лениво)

# ===== Единый event-loop агента (T-04) =====
# Агент живёт в своём постоянном loop (фоновый поток). Все обращения из
# синхронных HTTP-обработчиков идут через asyncio.run_coroutine_threadsafe
# к этому loop — так исчезает ошибка "bound to a different event loop",
# которая возникала при asyncio.run() внутри каждого обработчика.
_AGENT_LOOP = None
_AGENT_THREAD = None

# Reuse heavyweight local TTS models between requests.  Access is serialized because
# both Silero and Piper model objects are not guaranteed to be thread-safe.
_TTS_ENGINES: dict[tuple[str, str], Any] = {}
_TTS_ENGINE_LOCK = threading.RLock()

_TTS_VOICES = {
    "silero": [
        {"id": "xenia", "label": "Xenia — спокойная"},
        {"id": "kseniya", "label": "Kseniya — ясная"},
        {"id": "baya", "label": "Baya — мягкая"},
        {"id": "eugene", "label": "Eugene — мужской"},
        {"id": "aidar", "label": "Aidar — глубокий мужской"},
    ],
    "piper": [{"id": "ru_RU-irina-medium.onnx", "label": "Irina Medium — офлайн"}],
    "browser": [{"id": "", "label": "Системный русский голос браузера"}],
    "xtts": [{"id": "default", "label": "XTTS-v2 — голос по референсу сервера"}],
    "fish": [{"id": "default", "label": "Fish Audio — выразительный"}],
    "qwen_vc": [
        {"id": "cloned", "label": "Клонированный голос (Qwen VC)"},
        {"id": "default", "label": "Qwen Voice Clone — стандартный"},
    ],
}


def _bounded_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _tts_payload(body: dict[str, Any]) -> dict[str, Any]:
    provider = str(body.get("provider", "silero")).strip().lower()
    if provider not in _TTS_VOICES:
        raise ValueError(f"unknown TTS provider: {provider}")
    text = str(body.get("text", "")).strip()
    if not text:
        raise ValueError("text required")
    if len(text) > 8_000:
        raise ValueError("TTS text exceeds 8000 characters")
    qwen_ref_audio = str(body.get("qwen_ref_audio", "")).strip()
    if provider == "qwen_vc" and not qwen_ref_audio:
        qwen_ref_audio = str(Path(__file__).with_name("text.wav"))
    try:
        qwen_seed = int(body.get("qwen_seed", 1800013838))
    except (TypeError, ValueError):
        qwen_seed = 1800013838
    return {
        "provider": provider,
        "voice": str(body.get("voice", "")).strip()[:300],
        "text": text,
        "rate": _bounded_float(body.get("rate"), 1.0, 0.5, 2.0),
        "pitch": _bounded_float(body.get("pitch"), 0.0, -12.0, 12.0),
        "volume": _bounded_float(body.get("volume"), 1.0, 0.0, 1.5),
        "endpoint": str(body.get("endpoint", "")).strip()[:500],
        "qwen_ref_audio": qwen_ref_audio[:2000],
        "qwen_ref_text": str(body.get("qwen_ref_text", "")).strip()[:2000],
        "qwen_model_size": str(body.get("qwen_model_size", "1.7B")).strip()[:20],
        "qwen_seed": max(-1, min(2_147_483_647, qwen_seed)),
    }


def _external_tts(request: dict[str, Any]) -> tuple[bytes, str]:
    """Call an optional OpenAI-compatible XTTS/Fish HTTP service."""
    provider = request["provider"]
    endpoint = request["endpoint"] or os.environ.get(
        "UNI_XTTS_URL" if provider == "xtts" else "UNI_FISH_TTS_URL", ""
    )
    if not endpoint:
        raise RuntimeError(
            f"{provider.upper()} endpoint не настроен; укажите URL в панели или переменную окружения"
        )
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("TTS endpoint must use http or https")
    url = endpoint.rstrip("/")
    if not url.endswith(("/v1/audio/speech", "/v1/tts")):
        url += "/v1/audio/speech" if provider == "xtts" else "/v1/tts"
    payload = {
        "model": "xtts-v2" if provider == "xtts" else "s2",
        "input": request["text"],
        "text": request["text"],
        "voice": request["voice"] or "default",
        "speed": request["rate"],
        "pitch": request["pitch"],
        "volume": request["volume"],
        "format": "wav",
    }
    headers = {"Content-Type": "application/json", "Accept": "audio/wav,audio/mpeg,application/json"}
    token = os.environ.get("UNI_XTTS_API_KEY" if provider == "xtts" else "FISH_AUDIO_API_KEY", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read(40 * 1024 * 1024 + 1)
            content_type = response.headers.get("Content-Type", "audio/wav").split(";", 1)[0]
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace")
        raise RuntimeError(f"{provider.upper()} HTTP {exc.code}: {detail}") from exc
    if len(data) > 40 * 1024 * 1024:
        raise RuntimeError("TTS response exceeds 40 MB")
    if "json" in content_type:
        decoded = json.loads(data.decode("utf-8"))
        encoded = decoded.get("audio") or decoded.get("data")
        if not isinstance(encoded, str):
            raise RuntimeError("TTS JSON response has no audio field")
        import base64
        data = base64.b64decode(encoded)
        content_type = str(decoded.get("content_type") or "audio/wav")
    if not data:
        raise RuntimeError("TTS service returned empty audio")
    return data, "audio/mpeg" if "mpeg" in content_type or "mp3" in content_type else "audio/wav"


def _qwen_vc_tts(request: dict[str, Any]) -> tuple[bytes, str]:
    """Clone a voice via a Qwen Voice-Clone Gradio server (e.g. localhost:7860).

    The user runs their own Gradio TTS server; we call its unified TTS endpoint
    with the reference audio they supplied in the panel. Failures raise so the
    caller returns HTTP 502 — this path never crashes the whole server.
    """
    from gradio_client import Client, handle_file

    endpoint = request.get("endpoint") or "http://127.0.0.1:7860"
    if "://" not in endpoint:
        endpoint = "http://" + endpoint
    ref_audio = request.get("qwen_ref_audio") or ""
    ref_text = request.get("qwen_ref_text") or ""
    model_size = request.get("qwen_model_size") or "1.7B"
    seed = int(request.get("qwen_seed", 1800013838))
    # If the reference text is empty but a matching .txt sits next to the wav,
    # read it automatically (the user keeps text.wav + text.txt together).
    if not ref_text and ref_audio:
        candidate = Path(ref_audio).with_suffix(".txt")
        if candidate.is_file():
            try:
                ref_text = candidate.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                pass
    if not ref_audio:
        raise RuntimeError("Qwen VC: не указан путь к референс-аудио (поле qwen_ref_audio)")
    if not Path(ref_audio).is_file():
        raise RuntimeError(f"Qwen VC: файл референса не найден: {ref_audio}")
    ref_stat = Path(ref_audio).stat()
    cache_key = hashlib.sha256(json.dumps({
        "text": request["text"], "model": model_size, "seed": seed,
        "reference": str(Path(ref_audio).resolve()), "size": ref_stat.st_size,
        "mtime": ref_stat.st_mtime_ns,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    cache_dir = Path(__import__("tempfile").gettempdir()) / "uni_qwen_tts_cache"
    cache_file = cache_dir / f"{cache_key}.wav"
    if cache_file.is_file() and cache_file.stat().st_size > 44:
        return cache_file.read_bytes(), "audio/wav"
    client = Client(endpoint)
    # Real Gradio API (verified against the running server's /generate_unified_tts):
    #   text_input, tts_engine='Qwen Voice Clone', audio_format='wav',
    #   qwen_ref_audio_param, qwen_ref_text_param, qwen_language_param='Russian',
    #   qwen_clone_model_size_param, qwen_seed_param=-1
    api_name = "/generate_unified_tts"
    api = next((item for item in client.endpoints.values() if item.api_name == api_name), None)
    if api is None:
        raise RuntimeError(f"Qwen VC: Gradio endpoint {api_name} не найден")
    # This unified form marks even hidden controls of other engines as required.
    # Seed the call with the server's own defaults, then override only Qwen VC.
    params = {
        item["parameter_name"]: item.get("parameter_default")
        for item in api.parameters_info
    }
    params.update(
        text_input=request["text"],
        tts_engine="Qwen Voice Clone",
        audio_format="wav",
        qwen_mode="voice_clone",
        qwen_ref_audio=handle_file(ref_audio),
        qwen_ref_text=ref_text,
        qwen_language="Russian",
        qwen_xvector_only=False,
        qwen_clone_model_size=model_size,
        qwen_seed=seed,
    )
    result = client.predict(**params, api_name=api_name)
    # Gradio predict returns the audio file path (str) or (path, ...) tuple.
    if isinstance(result, (tuple, list)):
        result = result[0]
    if isinstance(result, dict):
        result = result.get("path") or result.get("name")
    if isinstance(result, str) and os.path.isfile(result):
        with open(result, "rb") as fh:
            data = fh.read()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(data)
        return data, "audio/wav"
    if isinstance(result, bytes):
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(result)
        return result, "audio/wav"
    raise RuntimeError(f"Qwen VC: неожиданный ответ сервера: {type(result)}")


def _ensure_agent_loop() -> asyncio.AbstractEventLoop | None:
    """Запускает (один раз) отдельный поток с постоянным event-loop агента.

    Возвращает loop или None, если агент ещё не инициализирован.
    """
    global _AGENT_LOOP, _AGENT_THREAD
    if _AGENT_LOOP is not None and not _AGENT_LOOP.is_closed():
        return _AGENT_LOOP
    agent = _CHAT_AGENT
    if agent is None:
        return None
    loop = getattr(agent, "_loop", None)
    if loop is None or loop.is_closed():
        return None
    _AGENT_LOOP = loop
    return _AGENT_LOOP


def _run_async(coro, timeout: float | None = 90.0):
    """Выполняет корутину в loop-е агента из синхронного обработчика.

    Если постоянный loop агента недоступен (агент не инициализирован как
    фоновый), откатывается к asyncio.run — поведение как раньше, но без
    утечки "different event loop" при наличии живого loop.
    """
    loop = _ensure_agent_loop()
    if loop is None:
        return asyncio.run(coro)
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _is_valid_base64(text: str) -> bool:
    """Validate a base64 blob without decoding the whole payload."""
    if not text or len(text) > 16_000_000:
        return False
    # Strip whitespace that some clients add.
    cleaned = "".join(text.split())
    if not cleaned:
        return False
    # Allow URL-safe alphabet too.
    import re as _re
    return bool(_re.fullmatch(r"[A-Za-z0-9+/=_-]*", cleaned)) and (len(cleaned) % 4 == 0)
# unknown falls through to application/octet-stream.
_STATIC_TYPES: dict[str, str] = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
}
_DEFAULT_PORT = 8787
_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_FILES = 12
_MAX_FILE_CHARS = 300_000
_MAX_TOTAL_FILE_CHARS = 1_000_000


def _scan_heartbeat(name: str) -> dict:
    """Read a heartbeat marker for participant <name> from uni-<name>/ if present."""
    d = _ROOT / f"uni-{name}"
    cand = None
    logs_dir = d / "logs"
    if logs_dir.is_dir():
        for f in logs_dir.glob("heartbeat*.txt"):
            cand = f
            break
    if cand is None:
        for f in d.glob("heartbeat*.txt"):
            cand = f
            break
    if cand is not None and cand.is_file():
        lines = cand.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        last = lines[-1] if lines else ""
        return {"file": str(cand.relative_to(_ROOT)), "last_line": last[:200],
                "online": bool(re.search(r"auto|ok|ready|готов|alive", last, re.I))}
    return {"file": None, "last_line": "", "online": False}


def _gather_participants() -> list[dict]:
    """Aggregate real council participants (source of truth) and enrich each
    with an on-disk heartbeat marker when a uni-<name>/ folder exists.

    🤖 Ground-truth (A-группа 11/13): participants come from load_participants()
    (where `hermes` is a real member) — NOT fabricated, and NOT dependent on a
    uni-* folder being present on disk. Folder scan only adds heartbeat status.
    """
    names: list[str] = []
    try:
        for p in load_participants():
            if p.name not in names:
                names.append(p.name)
    except Exception:
        pass
    # Also include any uni-* folders not listed in council specs (e.g. local agents).
    try:
        for d in sorted(_ROOT.iterdir()):
            if d.is_dir() and d.name.startswith("uni-"):
                extra = d.name[len("uni-"):]
                if extra not in names:
                    names.append(extra)
    except OSError:
        pass
    return [{"name": n, "heartbeat": _scan_heartbeat(n)} for n in names]


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if not length:
        return {}
    if length > _MAX_BODY_BYTES:
        raise ValueError(f"request is too large ({length} bytes)")
    raw = handler.rfile.read(length).decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _validated_files(raw: Any) -> dict[str, str]:
    """Return bounded UTF-8 text attachments suitable for an advisor prompt."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict) or len(raw) > _MAX_FILES:
        raise ValueError(f"files must be an object with at most {_MAX_FILES} entries")
    result: dict[str, str] = {}
    total = 0
    for raw_name, raw_text in raw.items():
        name = Path(str(raw_name)).name.strip()
        if not name or name in result or not isinstance(raw_text, str):
            raise ValueError("every attachment needs a unique file name and text content")
        if len(raw_text) > _MAX_FILE_CHARS:
            raise ValueError(f"attachment {name!r} exceeds {_MAX_FILE_CHARS} characters")
        total += len(raw_text)
        if total > _MAX_TOTAL_FILE_CHARS:
            raise ValueError("combined attachment text is too large")
        result[name] = raw_text
    return result


def _history(artifacts_dir: str, limit: int = 30) -> list[dict[str, Any]]:
    directory = (_ROOT / artifacts_dir).resolve()
    if not directory.is_relative_to(_ROOT.resolve()) or not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*_meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "round_id": data.get("round_id", path.stem.removesuffix("_meta")),
                "topic": data.get("topic", ""),
                "participants": data.get("participants", []),
                "signatures": len(data.get("signatures") or {}),
                "errors": len(data.get("errors") or {}),
                "report": (data.get("artifacts") or {}).get("report", ""),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return items


def _open_browser_hosts(cdp_url: str | None) -> set[str]:
    """Return hosts of currently open page tabs exposed by the browser CDP."""
    if not cdp_url:
        return set()
    endpoint = cdp_url.rstrip("/") + "/json"
    try:
        with urllib.request.urlopen(endpoint, timeout=2.0) as response:
            pages = json.loads(response.read(2_000_000).decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return set()
    hosts: set[str] = set()
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict) or page.get("type") != "page":
            continue
        host = (urlparse(str(page.get("url", ""))).hostname or "").lower()
        if host:
            hosts.add(host)
    return hosts


# R-02: рекурсивная маскировка секретов во всех JSON-ответах (defense-in-depth).
# Бэкенд и так не отдаёт сырые ключи (api_key_set: bool), но этот фильтр —
# страховка на случай, если какой-то эндпоинт вернёт api_key / sk-... / токен.
_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|access[_-]?token)")
_SECRET_VAL_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9_-]{8,}|AQ\.[A-Za-z0-9_.-]{8,}"
    r"|hf_[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})"
)

def _mask_value(v: str) -> str:
    # любое совпадение с паттерном секрета -> полная маскировка
    if _SECRET_VAL_RE.search(str(v)):
        return "***masked***"
    return str(v)

def _sanitize_secrets(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            ks = str(k)
            if _SECRET_KEY_RE.search(ks) or (isinstance(v, str) and _SECRET_VAL_RE.search(v)):
                out[k] = _mask_value(v)
            else:
                out[k] = _sanitize_secrets(v)
        return out
    if isinstance(obj, list):
        return [_sanitize_secrets(x) for x in obj]
    if isinstance(obj, str) and _SECRET_VAL_RE.search(obj):
        return _mask_value(obj)
    return obj



def _participant_statuses(cfg) -> list[dict[str, Any]]:
    statuses = []
    open_hosts = _open_browser_hosts(cfg.capabilities.browser.cdp_url)
    for participant in load_participants(min_interval_seconds=cfg.council.min_interval_seconds):
        status = "configured"
        detail = "configuration found"
        if participant.transport == "browser":
            if not cfg.council.browser_enabled:
                status, detail = "disabled", "browser adapter is disabled"
            else:
                expected = str(participant.spec.get("host", "")).lower()
                found = any(host == expected or host.endswith("." + expected) for host in open_hosts)
                if found:
                    status, detail = "ready", f"open tab found: {expected}"
                else:
                    status, detail = "configured", f"open tab not found: {expected}"
        elif participant.transport == "codex":
            command = participant.spec.get("command") or "codex"
            if shutil.which(command):
                status, detail = "ready", "Codex CLI found; saved login is used"
            else:
                status, detail = "unavailable", "Codex CLI was not found in PATH"
        elif participant.transport == "api":
            base_url = participant.spec.get("base_url", "")
            has_key = bool(participant.spec.get("_has_api_key"))
            local = urlparse(base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            if not base_url:
                status, detail = "unavailable", "base URL is missing"
            elif not local and not has_key:
                status, detail = "unavailable", "API key is missing"
            else:
                status, detail = "configured", "endpoint will be checked when the round starts"
        statuses.append({
            "name": participant.name,
            "role": participant.role,
            "transport": participant.transport,
            "free_tier": bool(participant.spec.get("free_tier", False)),
            "status": status,
            "detail": detail,
        })
    return statuses


async def _maybe_start_browser(cfg, selected):
    """Mirror uni.council.run browser bootstrap. Returns (session, participants)."""
    from uni.council.participants import Participant

    browser_participants = [p for p in selected if p.transport == "browser"]
    if not browser_participants:
        return None, selected

    # free_tier_only: drop paid browser participants.
    if cfg.council.free_tier_only:
        paid = [p for p in browser_participants if not p.is_free_tier_browser]
        for p in paid:
            print(f"[webui][skip] {p.name}: не бесплатный веб-уровень — запрещено "
                  f"(MANIFESTO v2.6 §7).", flush=True)
        browser_participants = [p for p in browser_participants if p.is_free_tier_browser]
        selected = [p for p in selected if p not in paid]

    if not cfg.council.browser_enabled:
        print("[webui] браузерный транспорт отключён в config.", flush=True)
        return None, [p for p in selected if p.transport != "browser"]

    try:
        from uni.browser_session import BrowserSession

        bc = cfg.capabilities.browser
        ac = getattr(bc, "agent_cursor", None)
        session = BrowserSession(
            user_data_dir=cfg.council.browser_profile,
            cdp_url=bc.cdp_url,
            agent_cursor_enabled=True if ac is None else bool(ac.enabled),
            agent_cursor_label="UNI" if ac is None else str(ac.label),
            agent_cursor_move_ms=220 if ac is None else int(ac.move_ms),
        )
        await session.start()
    except Exception as exc:  # pragma: no cover - depends on Playwright
        print(f"[webui][warn] браузер недоступен: {exc}. Браузерные участники пропущены.", flush=True)
        return None, [p for p in selected if p.transport != "browser"]

    for p in browser_participants:
        p.build_provider(browser_session=session, min_interval_seconds=cfg.council.min_interval_seconds)
    return session, selected


async def run_round(payload: dict, emit) -> dict:
    """Execute a real consensus round, streaming progress via ``emit`` (async)."""
    cfg = load_config()
    topic = (payload.get("topic") or "").strip() or "Без темы"
    brief = payload.get("brief", "")
    files = _validated_files(payload.get("files"))
    tasks = payload.get("tasks") or []
    only = payload.get("only") or None

    selected = load_participants(only=only, min_interval_seconds=cfg.council.min_interval_seconds)
    # Filter out participants the user turned off in the UI.
    if isinstance(payload.get("enabled"), list):
        enabled = set(payload["enabled"])
        selected = [p for p in selected if p.name in enabled]

    session, selected = await _maybe_start_browser(cfg, selected)
    if not selected:
        await emit({"type": "error", "msg": "Нет доступных участников (проверьте транспорт/браузер)."})
        return {}

    critic = next((p for p in selected if p.name == "Claude" and p.transport == "api"), None)
    coordinator = next((p for p in selected if p.name == "Hermes"), None)

    await emit({"type": "init", "participants": [
        {"name": p.name, "role": p.role, "transport": p.transport} for p in selected
    ]})

    round_ = CouncilRound(
        participants=selected,
        browser_session=session,
        artifacts_dir=cfg.council.artifacts_dir,
        concurrency=cfg.council.concurrency,
        timeout_seconds=cfg.council.timeout_seconds,
    )
    try:
        report = await round_.run(
            topic=topic, brief=brief, files=files, tasks=tasks,
            critic=critic, coordinator=coordinator, on_progress=emit,
        )
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
    return {
        "round_id": report.round_id,
        "signatures": report.signatures,
        "errors": report.errors,
        "synthesis": report.synthesis,
        "report_path": report.artifacts.get("report"),
    }


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive for SSE

    def log_message(self, *args):  # quieter logs
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Клиент разорвал соединение (например, отменил fetch при навигации) —
            # это не ошибка сервера, просто гасим, чтобы не засорять лог.
            pass

    def _json(self, code: int, value: Any) -> None:
        # R-02: любой JSON-ответ прогоняем через маскировку секретов (defense-in-depth)
        self._send(code, json.dumps(_sanitize_secrets(value), ensure_ascii=False).encode("utf-8"))

    def _redirect(self, location: str, code: int = 301) -> None:
        body = b""
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file_with_cache(self, path: Path, ctype: str, *, no_cache: bool = False) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if no_cache:
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_204(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        # === Единый лаунчер: статусы и логи (Hermes 2026-08-13) ===
        def _tcp_alive(host, port, timeout=1.0):
            import socket
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return True
            except Exception:
                return False

        def _uni_status():
            import json as _json_mod, subprocess as _sp
            pids = {}
            pf = _ROOT / "runtime" / "pids.json"
            try:
                pids = _json_mod.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                pids = {}
            def alive(pid):
                if not pid: return False
                try:
                    _sp.check_output(["tasklist", "/FI", f"PID eq {pid}"], stderr=_sp.DEVNULL)
                    return True
                except Exception:
                    return False
            # llama: порт 1235 + имя модели
            llama_running = _tcp_alive("127.0.0.1", 1235)
            model = None
            if llama_running:
                try:
                    import urllib.request
                    with urllib.request.urlopen("http://127.0.0.1:1235/v1/models", timeout=2) as r:
                        m = _json_mod.loads(r.read().decode("utf-8"))
                        if m.get("data"):
                            model = m["data"][0].get("id")
                except Exception:
                    pass
            # webui: порт 8787
            webui_running = _tcp_alive("127.0.0.1", 8787)
            # desktop (electron): PID из pids.json жив
            desktop_pid = (pids.get("electron") or {}).get("pid")
            desktop_running = alive(desktop_pid)
            # lmstudio: порт 1234 (опц.)
            lmstudio_reachable = _tcp_alive("127.0.0.1", 1234)
            return {
                "llama": {"running": llama_running, "pid": (pids.get("llama") or {}).get("pid"),
                          "port": 1235, "model": model,
                          # started_at в pids.json — в миллисекундах; time.time() — в секундах
                          "uptime_s": (int((time.time() * 1000 - (pids.get("started_at") or 0)) / 1000) if (llama_running and pids.get("started_at")) else 0)},
                "webui": {"running": webui_running, "pid": (pids.get("webui") or {}).get("pid"), "port": 8787},
                "desktop": {"running": desktop_running, "pid": desktop_pid},
                "lmstudio": {"reachable": lmstudio_reachable},
            }

        def _uni_logs(source, since=0):
            logs_dir = _ROOT / "runtime" / "logs"
            mapping = {
                "llama": logs_dir / "llama-server.log",
                "webui": logs_dir / "webui.log",
                "desktop": _HERE / "desktop.log",
            }
            f = mapping.get(source)
            if not f or not f.is_file():
                return []
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                return []
            lines = lines[-500:]
            if since and since < len(lines):
                lines = lines[since:]
            return [{"i": i, "t": ln} for i, ln in enumerate(lines[-200:])]

        if parsed.path == "/api/uni/status":
            self._json(200, _uni_status())
            return
        if parsed.path == "/api/uni/logs":
            src = parsed.query.get("source", "llama")
            try:
                since = int(parsed.query.get("since", "0") or 0)
            except Exception:
                since = 0
            self._json(200, {"source": src, "lines": _uni_logs(src, since)})
            return

        # === Самотест (Hermes 2026-08-13, §2): GET отдаёт последний отчёт/статус ===
        if parsed.path == "/api/selftest":
            self._json(200, _selftest_last())
            return
        # === Демо-мышь (Hermes 2026-08-13, §3): клик 3 точек в safe-зоне + рисунок ===
        if parsed.path == "/api/demo/mouse":
            self._json(200, _mouse_demo())
            return
        # === Скриншот оверлея (для пруфа/самотеста) ===
        if parsed.path == "/api/desktop/capture":
            self._json(200, _overlay_capture())
            return
        # === конец блока лаунчера ===

        def _kill_uni_children():
            """Убить все дочерние процессы Юни по runtime/pids.json (llama/webui/electron).
            Вызывается из /api/admin/stop и /api/stop — гарантирует, что 'Выход'/
            'Остановить всё' убивает ВЕСЬ стек, а не только пишет STOP.txt."""
            import json as _j, subprocess as _sp
            pf = _ROOT / "runtime" / "pids.json"
            pids = {}
            try:
                pids = _j.loads(pf.read_text(encoding="utf-8"))
            except Exception:
                pass
            targets = []
            for key in ("llama", "webui", "electron"):
                pid = (pids.get(key) or {}).get("pid")
                if pid:
                    targets.append((key, pid))
            for key, pid in targets:
                try:
                    _sp.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                            creationflags=0x08000000 if hasattr(_sp, "CREATE_NO_WINDOW") else 0)
                    log_message(f"[stop] killed {key} pid={pid}")
                except Exception as e:
                    log_message(f"[stop] kill {key} pid={pid} failed: {e}")
            try:
                pf.unlink(missing_ok=True)
            except Exception:
                pass

        if parsed.path in ("/api/admin/stop", "/api/stop"):
            # 🤖 Единый лаунчер: остановить ВЕСЬ стек Юни, а не только агента
            try:
                stop_file = (_ROOT / "STOP.txt").resolve()
                if stop_file.is_relative_to(_ROOT.resolve()):
                    stop_file.write_text(
                        "STOP\nСоздан: " + time.strftime("%Y-%m-%dT%H:%M:%S") +
                        "\nИсточник: admin (кнопка СТОП / трей Выход)\n",
                        encoding="utf-8",
                    )
                _kill_uni_children()
                self._json(200, {"stopped": True, "file": "STOP.txt", "killed_children": True})
            except OSError as exc:
                self._json(500, {"error": f"не удалось остановить: {exc}"})
            return

        if parsed.path in ("/favicon.ico",):
            # B-04: отдаём реальную иконку вместо 204-заглушки, чтобы вкладка
            # браузера не была без иконки.
            fav = (_HERE / "favicon.ico").resolve()
            if fav.is_file():
                self._send_file_with_cache(fav, "image/x-icon")
            else:
                self._send_204()
            return
        if parsed.path in ("/", "/index.html"):
            if _FRONTEND.exists():
                self._send_file_with_cache(_FRONTEND, "text/html; charset=utf-8", no_cache=True)
            else:
                self._send(404, b"frontend missing", "text/plain")
            return
        if parsed.path in ("/chat", "/chat.html"):
            # B-01: 301 редирект на единый SPA-интерфейс
            self._redirect("/", code=301)
            return
        if parsed.path in ("/remote-control", "/remote-control.html"):
            page = _HERE / "remote-control.html"
            if page.is_file():
                self._send_file_with_cache(page, "text/html; charset=utf-8", no_cache=True)
            else:
                self._send(404, b"remote controller missing", "text/plain")
            return
        if parsed.path in ("/camera-preview", "/camera-preview.html"):
            page = _HERE / "camera-preview.html"
            if page.is_file():
                self._send_file_with_cache(page, "text/html; charset=utf-8", no_cache=True)
            else:
                self._send(404, b"camera preview missing", "text/plain")
            return
        if parsed.path in ("/v3", "/v3/"):
            # R-01: админка v3 (отдельный SPA в uni/webui/v3/)
            page = _HERE / "v3" / "index.html"
            if page.is_file():
                self._send_file_with_cache(page, "text/html; charset=utf-8", no_cache=True)
            else:
                self._send(404, b"admin v3 missing", "text/plain")
            return

        if parsed.path in ("/api/context/feed", "/api/context/feed/"):
            self._handle_context_feed_get()
            return

        if parsed.path == "/api/tts/engines":
            engines = []
            for provider, voices in _TTS_VOICES.items():
                available = True
                detail = "готов"
                if provider == "xtts":
                    available = bool(os.environ.get("UNI_XTTS_URL"))
                    detail = "URL можно указать в панели" if not available else "UNI_XTTS_URL настроен"
                elif provider == "fish":
                    available = bool(os.environ.get("UNI_FISH_TTS_URL"))
                    detail = "URL можно указать в панели" if not available else "UNI_FISH_TTS_URL настроен"
                engines.append({"id": provider, "voices": voices, "available": available, "detail": detail})
            self._json(200, {"engines": engines})
            return

        # B-03: статика кешируется (max-age); браузер добавляет ?v= для инвалидации.
        # Отсекаем query-строку, чтобы /js/app.js?v=123 находил тот же файл.
        clean_path = parsed.path.split("?", 1)[0]
        _STATIC_ALIASES = {
            "/style.css": "css/style.css",
            "/app.js": "js/app.js",
            "/chat.js": "chat.js",
            "/chat.css": "css/chat.css",
            "/index.html": "index.html",
            # Фронтенд (Gemini) ссылается на static/*; физически файлы в js/ и css/.
            "/static/app.js": "js/app.js",
            "/static/style.css": "css/style.css",
        }

        if clean_path in _STATIC_ALIASES:
            candidate = (_HERE / _STATIC_ALIASES[clean_path]).resolve()
            if candidate.is_relative_to(_HERE.resolve()) and candidate.is_file():
                self._send_file_with_cache(candidate, _STATIC_TYPES[candidate.suffix.lower()])
                return
        if clean_path and not clean_path.startswith("/api/"):
            suffix = Path(clean_path).suffix.lower()
            if suffix in _STATIC_TYPES:
                rel = clean_path.lstrip("/")
                candidate = (_HERE / rel).resolve()
                if candidate.is_relative_to(_HERE.resolve()) and candidate.is_file():
                    self._send_file_with_cache(candidate, _STATIC_TYPES[suffix])
                    return

        if parsed.path == "/api/participants":
            cfg = load_config()
            self._json(200, _participant_statuses(cfg))
            return
        if parsed.path == "/api/history":
            cfg = load_config()
            self._json(200, _history(cfg.council.artifacts_dir))
            return

        # 🤖 T-04..T-08: админка v3 — агрегирующие эндпоинты (аддитивно, без изменения существующих)
        if parsed.path == "/api/global_state":
            # T-04: читает UNI_GLOBAL_STATE.md, возвращает JSON с содержимым
            p = (_ROOT / "uni" / "UNI_GLOBAL_STATE.md").resolve()
            if not p.is_relative_to(_ROOT.resolve()) or not p.is_file():
                self._json(404, {"error": "UNI_GLOBAL_STATE.md не найден"})
                return
            self._json(200, {"file": "uni/UNI_GLOBAL_STATE.md",
                             "content": p.read_text(encoding="utf-8", errors="replace")})
            return
        if parsed.path == "/api/tasks":
            # T-05: парсит UNI_BACKLOG.md, возвращает список задач со статусами
            p = (_ROOT / "UNI_BACKLOG.md").resolve()
            if not p.is_relative_to(_ROOT.resolve()) or not p.is_file():
                self._json(404, {"error": "UNI_BACKLOG.md не найден"})
                return
            text = p.read_text(encoding="utf-8", errors="replace")
            tasks = []
            for line in text.splitlines():
                m = re.match(r"^\s*##\s+(B-\d+|T-\d+)\s+(.*?)(\[V\]|\[ \]|\[solo\]|\[X\])?\s*$", line)
                if m:
                    tasks.append({"id": m.group(1), "title": m.group(2).strip(),
                                  "status": (m.group(3) or "").strip() or "open"})
                else:
                    m2 = re.match(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$", line)
                    if m2:
                        tasks.append({"id": "", "title": m2.group(2).strip(),
                                      "status": "done" if m2.group(1).lower() == "x" else "open"})
            self._json(200, {"file": "UNI_BACKLOG.md", "tasks": tasks})
            return
        if parsed.path == "/api/heartbeats":
            # T-06: участники из load_participants() (источник истины, включая
            # hermes) + heartbeat-статус из папок uni-<name>/ если есть.
            participants = _gather_participants()
            self._json(200, {"participants": participants})
            return

        if parsed.path == "/api/journal":
            # T-07: читает UNI_JOURNAL.jsonl, возвращает последние 100 записей
            p = (_ROOT / "UNI_JOURNAL.jsonl").resolve()
            if not p.is_relative_to(_ROOT.resolve()) or not p.is_file():
                self._json(404, {"error": "UNI_JOURNAL.jsonl не найден"})
                return
            rows = []
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            rows.append(json.loads(ln))
                        except json.JSONDecodeError:
                            rows.append({"raw": ln})
            except OSError:
                pass
            self._json(200, {"file": "UNI_JOURNAL.jsonl", "entries": rows[-100:]})
            return
        if parsed.path == "/api/participants_dirs":
            # T-08: список папок uni-* как участников
            parts = []
            try:
                for d in sorted(_ROOT.iterdir()):
                    if d.is_dir() and d.name.startswith("uni-"):
                        parts.append({"name": d.name[len("uni-"):], "dir": d.name,
                                      "has_logs": (d / "logs").is_dir()})
            except OSError:
                pass
            self._json(200, {"participants": parts})
            return

        # 🤖 DC-03 / DC-04: Desktop Companion — аддитивные эндпоинты (не ломают канон)
        if parsed.path == "/api/desktop/events":
            # SSE-поток событий для оверлея (смена уровня автономии, инициатива, статус наблюдения)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            _desktop_event_queue.put({"type": "hello", "ts": time.time()})
            try:
                while True:
                    try:
                        event = _desktop_event_queue.get(timeout=30.0)
                    except Exception:
                        try:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                            pass  # клиент ушёл — нормально
                        continue
                    line = json.dumps(event, ensure_ascii=False)
                    try:
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                        pass  # клиент ушёл — нормально
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if parsed.path == "/api/desktop/consent":
            # DC-04: GET — текущее согласие на наблюдение
            consent = _read_consent()
            self._json(200, consent)
            return

        if parsed.path == "/api/report":
            cfg = load_config()
            round_id = (parse_qs(parsed.query).get("id") or [""])[0]
            if not round_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in round_id):
                self._json(400, {"error": "invalid round id"})
                return

            report_path = (_ROOT / cfg.council.artifacts_dir / f"{round_id}_report.md").resolve()
            if not report_path.is_relative_to(_ROOT.resolve()) or not report_path.exists():
                self._json(404, {"error": "report not found"})
                return
            self._json(200, {"round_id": round_id, "markdown": report_path.read_text(encoding="utf-8")})
            return

        if parsed.path == "/api/config":
            cfg = load_config()
            data = {
                "browser_enabled": cfg.council.browser_enabled,
                "free_tier_only": cfg.council.free_tier_only,
                "min_interval_seconds": cfg.council.min_interval_seconds,
                "timeout_seconds": cfg.council.timeout_seconds,
                "concurrency": cfg.council.concurrency,
                "autonomous_enabled": cfg.autonomous.enabled,
                "auto_start_session": cfg.autonomous.auto_start_session,
                "endpoints": {
                    name: {
                        "base_url": ep.get("base_url", ""),
                        "api_key_set": bool(ep.get("api_key")),
                    }
                    for name, ep in cfg.council.api_endpoints.items()
                },
            }
            self._json(200, data)
            return

        if parsed.path == "/api/members":
            from uni.webui.council_api import list_members

            self._json(200, {"members": list_members()})
            return
        m = re.match(r"^/api/round/(\d+)$", parsed.path)
        if m:
            from uni.webui.council_api import get_round

            rec = get_round(int(m.group(1)))
            if rec is None:
                self._json(404, {"error": "round not found"})
            else:
                self._json(200, rec)
            return
        if parsed.path == "/api/history/delete":
            self.send_response(405, "Method Not Allowed")
            self.send_header("Allow", "POST")
            self.end_headers()
            return
        if parsed.path == "/api/safety":
            agent = self._get_chat_agent()
            guard = getattr(agent, "guard", None)
            if guard is None:
                self._json(503, {"error": "guard недоступен (агент не инициализирован)"})
                return
            cfg = guard.cfg
            self._json(200, {
                "autonomy_level": cfg.autonomy_level,
                "autonomy_active": bool(getattr(getattr(agent, "autonomous", None), "_tasks", set())),
            })
            return
        if parsed.path == "/api/roles":
            from uni.roles.loader import list_roles, get_current_role

            try:
                roles = list_roles()
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, {"roles": roles, "current": get_current_role()})
            return
        if parsed.path == "/api/role/prompt":
            # Просмотр system-prompt выбранной роли (для админ-панели).
            from uni.roles.loader import RoleLoader

            name = (parse_qs(parsed.query).get("role") or [""])[0].strip()
            if not name:
                self._json(400, {"error": "role required"})
                return
            try:
                role = RoleLoader().load(name)
                self._json(200, {"role": name, "prompt": role.system_prompt})
            except Exception as exc:
                self._json(404, {"error": f"{type(exc).__name__}: {exc}"})
            return

        if parsed.path == "/api/xtoys/status":
            agent = self._get_chat_agent()
            xtoys = agent.capabilities.get("xtoys") if agent is not None else None
            self._json(200, {
                "connected": xtoys is not None,
                "mode": "live" if xtoys is not None else "emulated",
            })
            return
        if parsed.path == "/api/xtoys/session/status":
            try:
                agent = self._get_chat_agent()
                session = self._xt_session(agent)
                self._json(200, {"active": session.active, "status": session.status_text()})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if parsed.path == "/api/intiface/status":
            try:
                if _INTIFACE is None:
                    self._json(200, {"connected": False, "url": "ws://127.0.0.1:12345", "devices": [], "last_error": ""})
                else:
                    self._json(200, _INTIFACE.status())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if parsed.path == "/api/xtoys/pattern/status":
            self._json(200, _XTOYS_PATTERN.status() if _XTOYS_PATTERN is not None else {
                "running": False, "name": "", "last_value": 0, "step": "", "error": ""
            })
            return
        if parsed.path == "/api/xtoys/motion/status":
            self._json(200, _MOTION.status() if _MOTION is not None else {"running": False, "region": {}, "value": 0, "error": None})
            return
        if parsed.path == "/api/xtoys/control/status":
            status = self._toy_coordinator().status()
            self._json(200, status)
            return
        if parsed.path == "/api/xtoys/remote/status":
            coordinator = self._toy_coordinator()
            session = coordinator.remote_session
            if session is not None and session.is_expired():
                coordinator.end_remote_session()
            self._json(200, coordinator.status().get("remote") or {"active": False, "connected": False})
            return
        # Autonomous UI bridge: stream phrases (text + audio_url) to the WebUI.
        if parsed.path == "/api/autonomous/stream":
            agent = self._get_chat_agent()
            state = getattr(agent, "state", None) if agent is not None else None
            queue = getattr(state, "ui_events", None) if state is not None else None
            if queue is None:
                self._json(503, {"error": "автономный режим не запущен"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            async def _stream_autonomous():
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        try:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                            pass  # клиент ушёл — нормально
                        continue
                    line = json.dumps(event, ensure_ascii=False)
                    try:
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                        pass  # клиент ушёл — нормально

            try:
                asyncio.run(_stream_autonomous())
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if parsed.path.startswith("/api/autonomous/audio/"):
            fname = parsed.path.rsplit("/", 1)[-1]
            # Serve only from the temp directory (no path traversal).
            import tempfile as _tf

            cand = Path(_tf.gettempdir()) / fname
            if cand.exists() and cand.is_file() and fname.startswith("uni_tts_"):
                content_type = "audio/mpeg" if cand.suffix.casefold() == ".mp3" else "audio/wav"
                self._send_file_with_cache(cand, content_type, no_cache=True)
            else:
                self._send(404, b"not found", "text/plain")
            return
        # B-02: SPA fallback — любой non-API путь (например, deep-link вкладки)
        # отдаёт index.html, чтобы фронтенд восстановил состояние из location.hash.
        if parsed.path and not parsed.path.startswith("/api/"):
            if _FRONTEND.exists():
                self._send_file_with_cache(_FRONTEND, "text/html; charset=utf-8", no_cache=True)
                return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        global _INTIFACE, _XTOYS_PATTERN, _MOTION, _REMOTE_TIMER, _REMOTE_ROOM_EVENTS, _REMOTE_ROOM_NEXT_ID
        # === Самотест / Демо-мышь / Скриншот (Hermes 2026-08-13) ===
        if self.path == "/api/selftest":
            body = self._read_json_body()
            if body.get("save"):
                try:
                    from uni.tools.selftest import run_all, save_report, render_markdown
                    checks = run_all()
                    p = save_report(checks)
                    log_message("[selftest] выполнен: " + p.name)
                    self._json(200, {"ok": True, "report_path": str(p),
                                      "checks": checks, "markdown": render_markdown(checks)})
                except Exception as e:
                    self._json(200, {"ok": False, "error": f"{type(e).__name__}: {e}"})
                return
            self._json(200, _selftest_last())
            return
        if self.path == "/api/demo/mouse":
            self._json(200, _mouse_demo())
            return
        if self.path == "/api/desktop/capture":
            self._json(200, _overlay_capture())
            return
        # === Единый лаунчер: перезапуск LLM (Hermes 2026-08-13) ===
        if self.path == "/api/admin/restart-llm":
            try:
                import json as _j, subprocess as _sp
                pf = _ROOT / "runtime" / "pids.json"
                try:
                    pids = _j.loads(pf.read_text(encoding="utf-8"))
                except Exception:
                    pids = {}
                old_pid = (pids.get("llama") or {}).get("pid")
                if old_pid:
                    try: _sp.run(["taskkill", "/F", "/PID", str(old_pid), "/T"], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, timeout=10)
                    except Exception: pass
                logs_dir = _ROOT / "runtime" / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                binp = _ROOT / "runtime" / "llama" / "llama-server.exe"
                model = _ROOT / "downloads" / "Qwen3-8B-Q4_K_M.gguf"
                if not binp.exists():
                    self._json(500, {"error": "llama-server.exe не найден"})
                    return
                logf = open(logs_dir / "llama-server.log", "a")
                p = _sp.Popen([str(binp), "--model", str(model), "--host", "127.0.0.1",
                               "--port", "1235", "--n-gpu-layers", "99", "--api-key", "uni-local"],
                              cwd=str(_ROOT), stdout=logf, stderr=logf,
                              creationflags=0x08000000)  # CREATE_NO_WINDOW
                pids["llama"] = {"pid": p.pid, "port": 1235}
                pf.write_text(_j.dumps(pids, indent=2), encoding="utf-8")
                self._json(200, {"restarted": True, "pid": p.pid})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        # 🤖 Единый лаунчер: остановить ВЕСЬ стек Юни (POST, для кнопки «Остановить всё»)
        if self.path in ("/api/admin/stop", "/api/stop"):
            try:
                import json as _j, subprocess as _sp
                pf = _ROOT / "runtime" / "pids.json"
                pids = {}
                try:
                    pids = _j.loads(pf.read_text(encoding="utf-8"))
                except Exception:
                    pass
                for key in ("llama", "webui", "electron"):
                    pid = (pids.get(key) or {}).get("pid")
                    if pid:
                        try:
                            _sp.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                                     stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                                     creationflags=0x08000000)
                        except Exception:
                            pass
                try:
                    pf.unlink(missing_ok=True)
                except Exception:
                    pass
                stop_file = (_ROOT / "STOP.txt").resolve()
                if stop_file.is_relative_to(_ROOT.resolve()):
                    stop_file.write_text("STOP\nСоздан: " + time.strftime("%Y-%m-%dT%H:%M:%S") +
                                         "\nИсточник: admin (кнопка СТОП / трей Выход)\n", encoding="utf-8")
                self._json(200, {"stopped": True, "file": "STOP.txt", "killed_children": True})
            except OSError as exc:
                self._json(500, {"error": f"не удалось остановить: {exc}"})
            return
        # 🤖 DC-04: POST — установить согласие на наблюдение (пишет журнал)
        if self.path == "/api/desktop/consent":
            # 🤖 DC-04: POST — установить согласие на наблюдение (пишет журнал)
            try:
                payload = _read_body(self)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            enabled = bool(payload.get("observation_enabled", False))
            level = str(payload.get("level", "off"))
            rec = _write_consent(enabled, level)
            self._json(200, rec)
            return
        if self.path == "/api/stop-cycle":
            # 🤖 Единый лаунчер / интерфейс: лёгкая остановка цикла Юни
            # (НЕ убивает серверы, в отличие от /api/admin/stop). Пишет STOP.txt
            # (event_loop проверяет его между циклами → прерывает цикл и озвучку)
            # и дёргает request_stop активного computer-use агента, если он есть.
            try:
                stop_file = (_ROOT / "STOP.txt").resolve()
                if stop_file.is_relative_to(_ROOT.resolve()):
                    stop_file.write_text(
                        "STOP\nСоздан: " + time.strftime("%Y-%m-%dT%H:%M:%S") +
                        "\nИсточник: интерфейс (кнопка STOP)\n", encoding="utf-8")
                agent = self._get_chat_agent()
                va = getattr(agent, "_last_visual_agent", None)
                stopped_va = False
                if va is not None and hasattr(va, "request_stop"):
                    try:
                        va.request_stop()
                        stopped_va = True
                    except Exception:
                        pass
                self._json(200, {"stopped": True, "stop_txt": True, "va_stopped": stopped_va})
            except OSError as exc:
                self._json(500, {"error": f"не удалось остановить цикл: {exc}"})
            return
        if self.path == "/api/desktop/suggest":
            # 🤖 D-13: POST — детектор событий + инициатива с бюджетом
            try:
                from uni.desktop.observe import suggest
            except Exception as exc:
                self._json(500, {"error": f"observe module error: {exc}"})
                return
            try:
                payload = _read_body(self)
                caption = str(payload.get("caption", ""))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, suggest(caption))
            return
        if self.path == "/api/desktop/act":
            # 🤖 D-14: POST — действие из белого списка через act_on_screen
            try:
                from uni.desktop.observe import act_allowed
            except Exception as exc:
                self._json(500, {"error": f"observe module error: {exc}"})
                return
            try:
                payload = _read_body(self)
                action = str(payload.get("action", ""))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            if not act_allowed(action):
                self._json(403, {"error": "действие не в белом списке", "allowed": list(
                    __import__("uni.desktop.observe", fromlist=["ACTION_WHITELIST"]).ACTION_WHITELIST.keys())})
                return
            # выполняем через agent.act_on_screen только для разрешённых действий
            try:
                agent = self._get_chat_agent()
                if agent is None or not hasattr(agent, "act_on_screen"):
                    self._json(501, {"error": "act_on_screen недоступен"})
                    return
                result = agent.act_on_screen(action, payload.get("param", ""))
                self._json(200, {"action": action, "result": str(result)})
            except Exception as exc:
                self._json(500, {"error": f"act error: {exc}"})
            return
        if self.path == "/api/stt":
            # 🤖 DC-02: POST — речь→текст (опциональный Whisper)
            try:
                from uni.capabilities.stt import transcribe_audio, engine_name
            except Exception as exc:
                self._json(500, {"error": f"stt module error: {exc}"})
                return
            try:
                eng = engine_name()
            except Exception as exc:
                self._json(500, {"error": f"stt engine load error: {exc}", "available": False})
                return
            if eng == "none":
                self._json(501, {"error": "STT engine (Whisper) не установлен", "available": False})
                return
            try:
                ctype = self.headers.get("Content-Type", "")
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    self._json(400, {"error": "пустое тело"})
                    return
                # поддержка multipart (form-data) и raw-байтов
                raw = self.rfile.read(length)
                mime = "audio/webm"
                if ctype.startswith("multipart/"):
                    boundary = ctype.split("boundary=")[-1].strip('"')
                    parts = raw.split(f"--{boundary}".encode())
                    for part in parts:
                        if b"filename=" in part and b"audio/" in part:
                            head, _, body = part.partition(b"\r\n\r\n")
                            raw = body.rstrip(b"\r\n")
                            mm = re.search(rb"audio/[a-zA-Z0-9.\-]+", head)
                            if mm:
                                mime = mm.group(0).decode("utf-8", "replace")
                            break
                # 🤖 FIX (Hermes, 2026-08-12): быстрый отказ на JSON-пробу / не-аудио
                # ДО загрузки тяжёлого движка Whisper (~7s первый вызов). Если тело
                # — валидный JSON (а не аудио), отвечаем 400 мгновенно, не загружая
                # модель. Это устраняет таймаут /api/stt на health/probe-запросах.
                stripped = raw.lstrip()
                if stripped[:1] in (b"{", b"["):
                    try:
                        json.loads(stripped)
                        self._json(400, {"error": "ожидается аудио (audio/*), а не JSON", "available": True})
                        return
                    except ValueError:
                        pass
                text = transcribe_audio(raw, mime)
                if text is None:
                    self._json(500, {"error": "не удалось распознать аудио", "available": True})
                    return
                self._json(200, {"text": text, "engine": eng})
            except (ValueError, OSError) as exc:
                self._json(400, {"error": f"некорректный запрос: {exc}"})
            return
        if self.path == "/api/round/start":
            try:
                payload = _read_body(self)
                _validated_files(payload.get("files"))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            async def _stream():
                queue: asyncio.Queue = asyncio.Queue()

                async def emit(event: dict):
                    await queue.put(event)

                async def worker():
                    try:
                        await run_round(payload, emit)
                    except Exception as exc:  # never kill the SSE socket on a round error
                        await emit({"type": "error", "msg": f"{type(exc).__name__}: {exc}"})

                task = asyncio.ensure_future(worker())
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        # heartbeat to keep the connection alive
                        try:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                            pass  # клиент ушёл — нормально
                        continue
                    line = json.dumps(event, ensure_ascii=False)
                    try:
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                        pass  # клиент ушёл — нормально
                    if event.get("type") == "done" or event.get("type") == "error":
                        break
                await task

            try:
                asyncio.run(_stream())
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path == "/api/config":
            try:
                self._save_config(_read_body(self))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True})
            return
        if self.path == "/api/history/delete":
            try:
                body = _read_body(self)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            round_id = (body.get("round_id") or "").strip()
            try:
                deleted = _delete_history(round_id)
                self._json(200, {"ok": True, "deleted": deleted})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        # ============ UNI Chat Hub (новый мультимодальный чат) ============
        if self.path == "/api/chat":
            self._handle_chat(self._read_json_body())
            return
        # 🤖 Универсальный UI-движок: поллинг статуса задачи/миссии (Директива §3, обязателен).
        # GET /api/task/<id>/status  и  GET /api/mission/<id>/status
        if self.path.startswith("/api/task/") and self.path.endswith("/status"):
            _tid = self.path.split("/")[-2]
            _evs = _UI_TASKS.get(_tid, [])
            self._json(200, {"task_id": _tid, "events": _evs, "finished": True,
                             "active": False})
            return
        if self.path.startswith("/api/mission/") and self.path.endswith("/status"):
            _mid = self.path.split("/")[-2]
            _evs = _UI_MISSIONS.get(_mid, [])
            self._json(200, {"mission_id": _mid, "events": _evs, "finished": True,
                             "active": False})
            return
        # 🤖 Действия пользователя из карточек (Директива U-07): POST /api/ui/action
        if self.path == "/api/ui/action":
            try:
                _b = self._read_json_body()
                _aid = str(_b.get("action_id", "")).strip()
                _tid = str(_b.get("task_id", "")).strip() or None
                # 🤖 U-05: карта id -> реальное действие; нет в карте -> честная ошибка
                # (НЕ молчаливый «ok»). Оркестратор в реальном агенте вызывает
                # action["handler"]; здесь возвращаем его, чтобы фронт/лог видели.
                result = resolve_action(_aid, _tid)
                if result.get("ok"):
                    # помечаем задачу исполненной (для честности поллинга)
                    if _tid and _tid in _UI_TASKS:
                        _UI_TASKS[_tid] = _UI_TASKS[_tid]  # на месте; действие логируется
                self._json(200 if result.get("ok") else 400, result)
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/camera/start":
            self._handle_camera_start(self._read_json_body())
            return
        if self.path == "/api/camera/stop":
            self._handle_camera_stop()
            return
        if self.path == "/api/vision/capture":
            self._handle_vision_capture(self._read_json_body())
            return
        if self.path in ("/api/context/feed", "/api/context/feed/"):
            if self.command == "POST":
                self._handle_context_feed_post(self._read_json_body())
            else:
                self._handle_context_feed_get()
            return
        if self.path == "/api/safety":
            self._handle_safety_post(self._read_json_body())
            return
        if self.path == "/api/xtoys":
            self._handle_xtoys()
            return
        if self.path == "/api/role/switch":
            try:
                body = self._read_json_body()
                name = str(body.get("role", "")).strip()
                from uni.roles.loader import RoleLoader, set_current_role

                role = RoleLoader().load(name)
                agent = self._get_chat_agent()
                if agent is not None:
                    agent.role = role
                    agent.event_loop.role_prompt = role.system_prompt
                    autonomous = getattr(agent, "autonomous", None)
                    if autonomous is not None and hasattr(autonomous, "role_prompt"):
                        autonomous.role_prompt = role.system_prompt
                global _XT_SESSION
                if _XT_SESSION is not None:
                    _XT_SESSION._role_prompt = role.system_prompt
                set_current_role(name)
                self._json(200, {"ok": True, "role": name, "prompt_loaded": bool(role.system_prompt)})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # TTS bridge: text -> browser SpeechSynthesis, local cached model, or optional
        # OpenAI-compatible XTTS/Fish service.
        if self.path in ("/api/tts", "/api/tts/test"):
            try:
                body = self._read_json_body()
                if self.path == "/api/tts/test" and not str(body.get("text", "")).strip():
                    body["text"] = "Привет. Это проверка выбранного голоса Юни."
                request = _tts_payload(body)
                provider = request["provider"]
                voice = request["voice"]
                if provider == "browser":
                    self._json(200, {"ok": True, "browser": True, "controls_applied": ["rate", "pitch", "volume"]})
                    return
                if provider in {"xtts", "fish"}:
                    data, content_type = _external_tts(request)
                    suffix = ".mp3" if content_type == "audio/mpeg" else ".wav"
                    import tempfile as _tf
                    out = Path(_tf.gettempdir()) / f"uni_tts_{int(time.time() * 1000)}{suffix}"
                    out.write_bytes(data)
                    self._json(200, {
                        "ok": True,
                        "audio_url": f"/api/autonomous/audio/{out.name}",
                        "content_type": content_type,
                        "controls_applied": ["rate", "pitch", "volume"],
                    })
                    return

                if provider == "qwen_vc":
                    data, content_type = _qwen_vc_tts(request)
                    suffix = ".wav" if content_type == "audio/wav" else ".mp3"
                    import tempfile as _tf
                    out = Path(_tf.gettempdir()) / f"uni_tts_{int(time.time() * 1000)}{suffix}"
                    out.write_bytes(data)
                    self._json(200, {
                        "ok": True,
                        "audio_url": f"/api/autonomous/audio/{out.name}",
                        "content_type": content_type,
                        "controls_applied": ["rate", "pitch", "volume"],
                    })
                    return

                from uni.capabilities.speech import SpeechCapability
                selected_voice = voice or ("ru_RU-irina-medium.onnx" if provider == "piper" else "xenia")
                # One Silero v5 model contains all supported speakers; only Piper
                # needs a separate cache entry per ONNX voice file.
                key = (provider, "v5_5_ru" if provider == "silero" else selected_voice)
                with _TTS_ENGINE_LOCK:
                    sp = _TTS_ENGINES.get(key)
                    if sp is None:
                        sp = SpeechCapability(
                            tts_provider=provider,
                            tts_voice=selected_voice,
                            silero_speaker=selected_voice if provider == "silero" else "xenia",
                            silero_sample_rate=48000,
                        )
                        _TTS_ENGINES[key] = sp
                    if provider == "silero":
                        sp.silero_speaker = selected_voice
                    wav = asyncio.run(sp.synthesize_to_wav(request["text"]))
                if wav is None:
                    self._json(502, {"error": "TTS не вернул аудио"})
                    return
                if request["volume"] != 1.0:
                    import soundfile as sf
                    audio, sample_rate = sf.read(wav, dtype="float32")
                    sf.write(wav, (audio * request["volume"]).clip(-1.0, 1.0), sample_rate, subtype="PCM_16")
                self._json(200, {
                    "ok": True,
                    "audio_url": f"/api/autonomous/audio/{wav.name}",
                    "content_type": "audio/wav",
                    "controls_applied": ["volume"],
                    "controls_note": "Темп и высота доступны для Browser, XTTS и Fish; локальные Silero/Piper применяют громкость.",
                })
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # Runtime autonomous start/stop (driven by the XToys "Автоматический режим" button).
        if self.path == "/api/autonomous/start":
            try:
                agent = self._get_chat_agent()
                ctrl = getattr(agent, "autonomous", None)
                if ctrl is None:
                    self._json(503, {"error": "автономный контроллер недоступен"})
                    return
                if getattr(ctrl, "_running", False):
                    self._json(200, {"ok": True, "already_running": True})
                    return
                ctrl.start()  # launches a background thread with its own asyncio loop
                self._json(200, {"ok": True, "running": True})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/autonomous/stop":
            try:
                agent = self._get_chat_agent()
                ctrl = getattr(agent, "autonomous", None)
                if ctrl is None:
                    self._json(503, {"error": "автономный контроллер недоступен"})
                    return
                asyncio.run(ctrl.stop())
                self._json(200, {"ok": True, "running": False})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # ===== XToys autonomous session: device timeline + synced speech =====
        if self.path == "/api/xtoys/session/start":
            try:
                agent = self._get_chat_agent()
                session = self._xt_session(agent)
                if session.active:
                    self._json(200, {"ok": True, "already_running": True})
                    return
                if _XTOYS_PATTERN is not None:
                    _XTOYS_PATTERN.stop()
                    _XTOYS_PATTERN = None
                if _MOTION is not None and _MOTION.status().get("running"):
                    self._xt_run(_MOTION.stop(), timeout=8)
                coordinator = self._toy_coordinator()
                self._xt_run(coordinator.stop(), timeout=5)
                if not self._xt_run(coordinator.acquire(AUTONOMOUS), timeout=5):
                    self._json(409, {"error": "аварийный стоп активен"})
                    return
                # fire-and-forget: session.start() opens the browser/xtoys and may
                # take a while; the UI polls /status instead of blocking here.
                self._xt_fire(session.start(open_xtoys=False, confirm_ready=False))
                self._json(200, {"ok": True, "running": True, "message": "запуск сессии…"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/session/stop":
            try:
                agent = self._get_chat_agent()
                session = self._xt_session(agent)
                msg = self._xt_run(session.stop())
                self._xt_run(self._toy_coordinator().release(AUTONOMOUS), timeout=5)
                self._json(200, {"ok": True, "running": False, "message": msg})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/session/intensity":
            try:
                body = self._read_json_body()
                value = int(body.get("value", 0))
                agent = self._get_chat_agent()
                session = self._xt_session(agent)
                if session.active:
                    msg = session.set_manual_override(value)
                res = self._xt_run(self._run_xtoys_device_tool("xtoys.set_intensity", {"value": value}, MANUAL))
                if not session.active:
                    msg = getattr(res, "message", "ok")
                ok = bool(getattr(res, "success", False))
                self._json(200 if ok else 502, {"ok": ok, "value": value, "message": msg, "error": None if ok else msg})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/session/status":
            try:
                agent = self._get_chat_agent()
                session = self._xt_session(agent)
                self._json(200, {"active": session.active, "status": session.status_text()})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # ===== Motion-to-Toy =====
        if self.path == "/api/xtoys/motion/region":
            try:
                body = self._read_json_body()
                coordinator = self._toy_coordinator()
                if _MOTION is None:
                    _MOTION = MotionToyController(coordinator)
                _MOTION.set_region(body)
                self._json(200, {"ok": True, "region": _MOTION.status()["region"]})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/motion/start":
            try:
                body = self._read_json_body()
                coordinator = self._toy_coordinator()
                if _MOTION is None:
                    _MOTION = MotionToyController(coordinator)
                region = body.get("region") or {}
                if region:
                    _MOTION.set_region(region)
                settings = MotionSettings(
                    source="camera" if body.get("source") == "camera" else "screen",
                    left=int((_MOTION.status().get("region") or {}).get("left", 0)),
                    top=int((_MOTION.status().get("region") or {}).get("top", 0)),
                    width=int((_MOTION.status().get("region") or {}).get("width", 0)),
                    height=int((_MOTION.status().get("region") or {}).get("height", 0)),
                    threshold=float(body.get("threshold", 2.6)),
                    gain=float(body.get("gain", 10.0)),
                    smoothing=max(0.0, min(1.0, float(body.get("smoothing", 0.95)))),
                    period_ms=max(50, min(1000, int(body.get("period_ms", 140)))),
                    max_intensity=max(0.0, min(100.0, float(body.get("max_intensity", 70)))),
                    gamma=max(0.2, min(5.0, float(body.get("gamma", 3.7)))),
                )
                if _XTOYS_PATTERN is not None:
                    _XTOYS_PATTERN.stop()
                    _XTOYS_PATTERN = None
                session = self._xt_session(self._get_chat_agent())
                if session.active:
                    self._xt_run(session.stop(), timeout=10)
                self._xt_run(coordinator.stop(), timeout=5)
                if not self._xt_run(coordinator.acquire(MOTION), timeout=5):
                    self._json(409, {"error": "машинка занята другим режимом"})
                    return
                self._xt_run(_MOTION.start(settings), timeout=5)
                self._json(200, {"ok": True, **_MOTION.status()})
            except Exception as exc:
                try:
                    self._xt_run(self._toy_coordinator().release(MOTION), timeout=5)
                except Exception:
                    pass
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/motion/stop":
            try:
                if self.headers.get("Content-Length"):
                    self._read_json_body()
                if _MOTION is not None:
                    self._xt_run(_MOTION.stop(), timeout=8)
                self._xt_run(self._toy_coordinator().release(MOTION), timeout=5)
                self._json(200, {"ok": True})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # ===== Local, owner-approved remote control =====
        if self.path == "/api/xtoys/remote/session/start":
            try:
                body = self._read_json_body()
                coordinator = self._toy_coordinator()
                self._xt_run(coordinator.stop(), timeout=5)
                session = coordinator.create_remote_session(
                    max_intensity=max(0, min(100, float(body.get("max_intensity", 40)))),
                    ttl=max(60, min(3600, float(body.get("ttl", 1800)))),
                )
                with _REMOTE_ROOM_LOCK:
                    _REMOTE_ROOM_EVENTS = []
                    _REMOTE_ROOM_NEXT_ID = 1
                host = self.headers.get("Host", "127.0.0.1:8787")
                self._json(200, {"ok": True, "url": f"http://{host}/remote-control#token={session.token}", "expires_in": session.ttl})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/remote/session/stop":
            try:
                if self.headers.get("Content-Length"):
                    self._read_json_body()
                if _REMOTE_TIMER is not None:
                    _REMOTE_TIMER.cancel()
                    _REMOTE_TIMER = None
                coordinator = self._toy_coordinator()
                coordinator.end_remote_session()
                _stop_public_tunnel()
                with _REMOTE_ROOM_LOCK:
                    _REMOTE_ROOM_EVENTS = []
                    _REMOTE_ROOM_NEXT_ID = 1
                self._xt_run(coordinator.release(REMOTE), timeout=5)
                self._json(200, {"ok": True})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/remote/public/start":
            try:
                if self.headers.get("Content-Length"):
                    self._read_json_body()
                coordinator = self._toy_coordinator()
                session = coordinator.remote_session
                if session is None or session.is_expired():
                    self._json(409, {"error": "сначала создайте Remote-сессию"})
                    return
                public_base = _start_public_tunnel()
                self._json(200, {"ok": True, "url": f"{public_base}/remote-control#token={session.token}"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/remote/public/stop":
            if self.headers.get("Content-Length"):
                self._read_json_body()
            _stop_public_tunnel()
            self._json(200, {"ok": True})
            return
        if self.path == "/api/xtoys/remote/public/status":
            if self.headers.get("Content-Length"):
                self._read_json_body()
            running = _PUBLIC_TUNNEL_PROCESS is not None and _PUBLIC_TUNNEL_PROCESS.poll() is None
            self._json(200, {"ok": True, "running": running, "base_url": _PUBLIC_TUNNEL_URL if running else ""})
            return
        if self.path == "/api/xtoys/remote/room":
            try:
                body = self._read_json_body()
                token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip() or str(body.get("token", ""))
                coordinator = self._toy_coordinator()
                session = coordinator.remote_session
                if session is None or session.is_expired() or not token or not __import__("hmac").compare_digest(token, session.token):
                    self._json(403, {"error": "remote session invalid or expired"})
                    return
                role = str(body.get("role", "")).strip()
                if role not in {"owner", "controller"}:
                    self._json(400, {"error": "invalid room role"})
                    return
                action = str(body.get("action", "poll"))
                if action == "send":
                    kind = str(body.get("kind", ""))
                    if kind not in {"offer", "answer", "ice", "chat", "hangup"}:
                        self._json(400, {"error": "invalid room event"})
                        return
                    payload = body.get("payload")
                    encoded = json.dumps(payload, ensure_ascii=False)
                    if len(encoded.encode("utf-8")) > 131072:
                        self._json(413, {"error": "room event too large"})
                        return
                    target = "controller" if role == "owner" else "owner"
                    with _REMOTE_ROOM_LOCK:
                        event = {"id": _REMOTE_ROOM_NEXT_ID, "kind": kind, "from": role, "target": target, "payload": payload, "time": time.time()}
                        _REMOTE_ROOM_NEXT_ID += 1
                        _REMOTE_ROOM_EVENTS.append(event)
                        del _REMOTE_ROOM_EVENTS[:-500]
                    self._json(200, {"ok": True, "id": event["id"]})
                    return
                after = max(0, int(body.get("after", 0)))
                with _REMOTE_ROOM_LOCK:
                    events = [event for event in _REMOTE_ROOM_EVENTS if event["id"] > after and event["target"] == role]
                self._json(200, {"ok": True, "events": events[-100:]})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path in ("/api/xtoys/remote/control", "/api/xtoys/remote/heartbeat"):
            try:
                origin = self.headers.get("Origin", "").rstrip("/")
                host = self.headers.get("Host", "")
                if origin and origin not in {f"http://{host}", f"https://{host}"}:
                    self._json(403, {"error": "remote origin rejected"})
                    return
                body = self._read_json_body()
                token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip() or str(body.get("token", ""))
                coordinator = self._toy_coordinator()
                session = coordinator.remote_session
                if session is None or session.is_expired() or not token or not __import__("hmac").compare_digest(token, session.token):
                    self._json(403, {"error": "remote session invalid or expired"})
                    return
                sequence = int(body.get("sequence", session.sequence + 1))
                if sequence <= session.sequence:
                    self._json(409, {"error": "stale command"})
                    return
                session.sequence = sequence
                session.connected = True
                session.last_heartbeat = time.time()
                if self.path.endswith("/control"):
                    value = max(0.0, min(session.max_intensity, float(body.get("value", 0))))
                    if not self._xt_run(coordinator.set_intensity(REMOTE, value), timeout=5):
                        self._json(409, {"error": "машинка занята другим режимом"})
                        return
                if _REMOTE_TIMER is not None:
                    _REMOTE_TIMER.cancel()
                _REMOTE_TIMER = threading.Timer(2.5, _remote_timeout_stop)
                _REMOTE_TIMER.daemon = True
                _REMOTE_TIMER.start()
                self._json(200, {"ok": True, "value": coordinator.current_value, "max_intensity": session.max_intensity})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/emergency-stop":
            try:
                if self.headers.get("Content-Length"):
                    self._read_json_body()
                if _MOTION is not None:
                    self._xt_run(_MOTION.stop(), timeout=8)
                if _XTOYS_PATTERN is not None:
                    _XTOYS_PATTERN.stop()
                    _XTOYS_PATTERN = None
                self._xt_run(self._toy_coordinator().emergency_stop(), timeout=8)
                self._json(200, {"ok": True})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/emergency-reset":
            if self.headers.get("Content-Length"):
                self._read_json_body()
            self._toy_coordinator().reset_emergency()
            self._json(200, {"ok": True})
            return
        # ===== Intiface (Buttplug) direct bridge =====
        if self.path == "/api/intiface/connect":
            try:
                url = (self._read_json_body().get("url") or "ws://127.0.0.1:12345") if self.headers.get("Content-Length") else "ws://127.0.0.1:12345"
                if _INTIFACE is None:
                    _INTIFACE = IntifaceBridge(url)
                else:
                    _INTIFACE.url = url
                agent = self._get_chat_agent()
                # fire-and-forget: connect may take a moment; UI polls /status.
                self._xt_fire(_INTIFACE.connect())
                self._json(200, {"ok": True, "connecting": True, "message": "подключение к Intiface…"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/intiface/disconnect":
            try:
                if _INTIFACE is not None:
                    res = self._xt_run(_INTIFACE.disconnect(), timeout=10)
                else:
                    res = {"ok": True, "connected": False}
                self._json(200, res)
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/intiface/oscillate":
            try:
                body = self._read_json_body()
                value = int(body.get("value", 0))
                if _INTIFACE is None:
                    _INTIFACE = IntifaceBridge("ws://127.0.0.1:12345")
                res = self._xt_run(self._run_xtoys_device_tool("xtoys.set_intensity", {"value": value}, MANUAL), timeout=10)
                self._json(200 if res.success else 409, {"ok": res.success, "value": value, "error": None if res.success else res.message})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/intiface/stop":
            try:
                if _INTIFACE is not None:
                    coordinator = self._toy_coordinator()
                    self._xt_run(coordinator.stop(), timeout=10)
                    res = {"ok": True}
                else:
                    res = {"ok": True}
                self._json(200, res)
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/intiface/status":
            try:
                if _INTIFACE is None:
                    self._json(200, {"connected": False, "url": "ws://127.0.0.1:12345", "devices": [], "last_error": ""})
                else:
                    self._json(200, _INTIFACE.status())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # ===== UNI «Компьютер»: зрение -> действие -> проверка =====
        if self.path == "/api/computer/act":
            try:
                body = self._read_json_body()
                goal = str(body.get("goal", "")).strip()
                max_steps = int(body.get("max_steps", 8))
                if not goal:
                    self._json(400, {"error": "пустая цель"})
                    return
                agent = self._get_chat_agent()

                async def _run():
                    return await agent.act_on_screen(goal, max_steps=max_steps)

                # fire-and-forget: цикл может идти долго; UI опрашивает статус
                task = self._xt_fire(_run())
                self._json(200, {"ok": True, "accepted": True, "goal": goal, "message": "команда принята, Юни выполняет под зрением"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/computer/stop":
            try:
                agent = self._get_chat_agent()
                va = getattr(agent, "_last_visual_agent", None)
                if va is not None:
                    va.request_stop()
                    self._json(200, {"ok": True, "stopped": True})
                else:
                    self._json(200, {"ok": True, "stopped": False, "message": "нет активного цикла"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/computer/status":
            try:
                agent = self._get_chat_agent()
                va = getattr(agent, "_last_visual_agent", None)
                if va is not None:
                    st = va.status()
                    self._json(200, st)
                else:
                    self._json(200, {"active": False, "steps": 0, "stopped": False, "message": "нет активного цикла"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # ===== Dorch neutral motion profiles =====
        if self.path == "/api/xtoys/pattern/list":
            try:
                self._json(200, {"patterns": PATTERN_NAMES})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/pattern/start":
            try:
                body = self._read_json_body()
                name = str(body.get("name", "")).strip().lower()
                duration = float(body.get("duration", 20.0))
                intensity = int(body.get("intensity", 70))
                if name not in PATTERN_NAMES:
                    self._json(400, {"error": f"unknown pattern: {name}", "available": PATTERN_NAMES})
                    return
                if _INTIFACE is None or not _INTIFACE.connected:
                    self._json(503, {"error": "Сначала подключите Intiface"})
                    return
                if _XTOYS_PATTERN is None:
                    _XTOYS_PATTERN = XToysPatternEngine(run_tool=lambda name, args: self._run_xtoys_device_tool(name, args, PATTERN))
                coordinator = self._toy_coordinator()
                if _MOTION is not None and _MOTION.status().get("running"):
                    self._xt_run(_MOTION.stop(), timeout=8)
                session = self._xt_session(self._get_chat_agent())
                if session.active:
                    self._xt_run(session.stop(), timeout=10)
                self._xt_run(coordinator.stop(), timeout=5)
                if not self._xt_run(coordinator.acquire(PATTERN), timeout=5):
                    self._json(409, {"error": "аварийный стоп активен"})
                    return
                # fire-and-forget: pattern runs in the agent's live loop
                self._xt_fire(self._run_pattern(_XTOYS_PATTERN, name, duration, intensity))
                self._json(200, {"ok": True, "running": name, "message": f"паттерн «{name}» запущен"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/pattern/stop":
            try:
                if _XTOYS_PATTERN is not None:
                    _XTOYS_PATTERN.stop()
                    _XTOYS_PATTERN = None
                if _INTIFACE is not None and _INTIFACE.connected:
                    self._xt_run(self._toy_coordinator().release(PATTERN), timeout=5)
                self._json(200, {"ok": True, "message": "паттерн остановлен"})
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if self.path == "/api/xtoys/pattern/status":
            try:
                if _XTOYS_PATTERN is None:
                    self._json(200, {"running": False, "name": "", "last_value": 0, "step": "", "error": ""})
                else:
                    self._json(200, _XTOYS_PATTERN.status())
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # --- гибридный слой «отправка заданий участникам» ---
        if self.path == "/api/round":
            from uni.webui.council_api import create_round

            body = self._read_json_body()
            task = str(body.get("task", "")).strip()
            members = body.get("members")
            if not task:
                self._json(400, {"error": "task обязателен"})
                return
            try:
                result = _run_async(create_round(task, members))
                self._json(200, result)
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        mp = re.match(r"^/api/round/(\d+)/paste$", self.path)
        if mp:
            from uni.webui.council_api import paste_response

            body = self._read_json_body()
            member = str(body.get("member", "")).strip()
            text = str(body.get("text", ""))
            rec = paste_response(int(mp.group(1)), member, text)
            if rec is None:
                self._json(404, {"error": "round или участник не найден"})
            else:
                self._json(200, {"ok": True, "round_id": rec["round_id"]})
            return
        # ====================== конец Chat Hub ======================
        self._send(404, b"not found", "text/plain")

    def _read_json_body(self) -> dict:
        try:
            return json.loads((self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)).decode("utf-8") or "{}")
        except (ValueError, KeyError, TypeError):
            return {}

    # ---------- UNI Chat Hub (мультимодальный чат) ----------
    def _xt_session(self, agent):
        """Create/cache the XToys autonomous session bound to this agent.

        Drives the device through the xtoys capability (xtoys.app → Intiface) and
        speaks via the speech capability — no raw browser socket involved.
        """
        global _XT_SESSION
        if _XT_SESSION is not None and getattr(_XT_SESSION, "state", None) is not None:
            return _XT_SESSION
        speech = agent.capabilities.get("speech")
        cfg = getattr(agent, "config", None)
        max_int = 50
        role_prompt = ""
        if cfg is not None:
            max_int = getattr(getattr(cfg, "capabilities", None), "xtoys", None)
            max_int = getattr(max_int, "max_intensity", 50) if max_int else 50
            role = getattr(getattr(cfg, "autonomous", None), "role_prompt", "") or ""
            role_prompt = role
        _XT_SESSION = AutonomousSession(
            run_tool=lambda name, args: self._run_xtoys_device_tool(name, args, AUTONOMOUS),
            speak=(lambda t: speech.speak(t)) if speech is not None else (lambda t: False),
            chat=agent.brain.chat,
            role_prompt=role_prompt or "Ты — властная госпожа в автономной сессии с секс-машинкой.",
            max_intensity=max_int,
        )
        return _XT_SESSION

    def _toy_coordinator(self) -> ToyControlCoordinator:
        global _INTIFACE, _TOY_COORDINATOR
        if _INTIFACE is None:
            _INTIFACE = IntifaceBridge("ws://127.0.0.1:12345")
        agent = self._get_chat_agent()
        loop = getattr(agent, "_loop", None)
        if _TOY_COORDINATOR is None or getattr(_TOY_COORDINATOR, "_bridge", None) is not _INTIFACE:
            _TOY_COORDINATOR = ToyControlCoordinator(_INTIFACE, loop=loop)
        elif loop is not None:
            _TOY_COORDINATOR._loop = loop
        return _TOY_COORDINATOR

    async def _run_pattern(self, engine: XToysPatternEngine, name: str, duration: float, intensity: int) -> None:
        try:
            await engine.run(name, duration, intensity)
        finally:
            await self._toy_coordinator().release(PATTERN)

    async def _run_xtoys_device_tool(self, name: str, args: dict[str, Any], source: str = MANUAL) -> ToolResult:
        """Route all panel/session/pattern device control through Intiface."""
        global _INTIFACE
        action = name.rsplit(".", 1)[-1]
        if _INTIFACE is None or not _INTIFACE.connected:
            return ToolResult(success=False, message="Intiface не подключён")
        coordinator = self._toy_coordinator()
        if action in {"set_intensity", "ramp_intensity"}:
            value = int(args.get("value", 0))
            ok = await coordinator.set_intensity(source, value)
            if not ok and source == AUTONOMOUS:
                await coordinator.stop()
                await coordinator.acquire(AUTONOMOUS)
                ok = await coordinator.set_intensity(AUTONOMOUS, value)
            result = {"ok": ok, "value": coordinator.current_value, "error": None if ok else "источник управления занят или аварийно остановлен"}
        elif action == "read_intensity":
            result = {"ok": True, "value": coordinator.current_value}
        elif action == "get_status":
            intiface_status = _INTIFACE.status()
            result = {
                "ok": True,
                "visible_text": "connected " + " ".join(intiface_status["devices"]),
                "connected": bool(intiface_status.get("connected")),
                "devices": intiface_status.get("devices", []),
                "value": coordinator.current_value,
                "active_source": coordinator.active_source,
            }
        elif action == "open":
            result = {"ok": True}
        elif action == "stop":
            await coordinator.release(source)
            result = {"ok": True, "value": 0}
        else:
            return ToolResult(success=False, message=f"Неподдерживаемое действие Intiface: {action}")
        return ToolResult(
            success=bool(result.get("ok")),
            data=result,
            message=result.get("error") or f"Intiface {action}: {result.get('value', 'ok')}",
        )

    def _xt_run(self, coro, timeout: float = 90):
        """Schedule a coroutine on the agent's live loop; used for quick calls."""
        agent = self._get_chat_agent()
        loop = getattr(agent, "_loop", None)
        if loop is None:
            raise RuntimeError("agent runtime loop недоступен")
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)

    def _xt_fire(self, coro):
        """Fire-and-forget a coroutine on the agent's live loop (no blocking wait)."""
        agent = self._get_chat_agent()
        loop = getattr(agent, "_loop", None)
        if loop is None:
            raise RuntimeError("agent runtime loop недоступен")
        asyncio.run_coroutine_threadsafe(coro, loop)
        return None

    def _get_chat_agent(self):
        global _CHAT_AGENT
        if _CHAT_AGENT is None or getattr(_CHAT_AGENT, "_closed", False):
            from uni.agent import Agent

            cfg = load_config()
            agent = Agent(cfg)
            # T-04: инициализируем агента в отдельном потоке с постоянным
            # event-loop, чтобы все последующие вызовы (run_cycle, camera.*)
            # шли в ОДИН loop — убирает "bound to a different event loop".
            self._start_agent_runtime(agent, cfg)
            _CHAT_AGENT = agent
        return _CHAT_AGENT

    def _start_agent_runtime(self, agent, cfg) -> None:
        """Запускает initialize() агента в фоновом потоке с живым loop.

        loop сохраняется в agent._loop и переиспользуется всеми HTTP-
        обработчиками через _run_async(). Если initialize падает (нет
        LM Studio / браузера) — loop всё равно жив, агент помечается
        _init_error и продолжает отвечать текстом.
        """
        import threading

        init_error = {}

        def _bootstrap():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            agent._loop = loop
            try:
                loop.run_until_complete(
                    asyncio.wait_for(agent.initialize(), timeout=20.0)
                )
            except asyncio.TimeoutError:
                # Медленный прогрев Speech не должен блокировать уже доступный
                # текстовый чат. wait_for отменил прогрев; loop остаётся рабочим.
                agent._init_warning = "initialize timeout; text chat enabled"
            except Exception as exc:  # агент без тяжёлых capability отвечает текстом
                agent._init_error = f"{type(exc).__name__}: {exc}"
                init_error["err"] = agent._init_error
            # Keep processing run_coroutine_threadsafe() calls from HTTP handlers.
            # Previously the thread returned here, leaving a valid-looking but
            # stopped loop; XToys/Intiface commands were queued forever.
            loop.run_forever()

        t = threading.Thread(target=_bootstrap, name="uni-agent-loop", daemon=True)
        t.start()
        t.join(timeout=10.0)  # ждём initialize, но не блокируем вечно
        # если initialize ещё идёт — loop уже жив, дальше доинициализируется


    def _get_feed(self):
        global _CHAT_FEED
        if _CHAT_FEED is None:
            from uni.context.feed_injector import ContextFeedInjector

            cfg = load_config()
            _CHAT_FEED = ContextFeedInjector(allow_external_scrape=cfg.context.allow_external_scrape)
            for url in cfg.context.feeds:
                _CHAT_FEED.add_feed_url(url)
        return _CHAT_FEED

    def _handle_chat(self, body: dict) -> None:
        # Принимаем text ИЛИ message (обратно совместимо с фронтендом панели)
        text = (body.get("text") or body.get("message") or "").strip()
        if not text:
            self._json(400, {"error": "empty text"})
            return
        agent = self._get_chat_agent()
        cfg = load_config()
        init_error = getattr(agent, "_init_error", None)
        if init_error:
            self._json(503, {"error": "agent init failed", "detail": init_error,
                             "hint": "проверь config.yaml (модель/браузер) на машине запуска"})
            return
        # подстановка роли, если фронтенд передал role и агент её поддерживает
        role = (body.get("role") or "").strip()
        if role and hasattr(agent, "event_loop"):
            try:
                from uni.roles.loader import RoleLoader
                loaded_role = RoleLoader().load(role)
                agent.role = loaded_role
                agent.event_loop.role_prompt = loaded_role.system_prompt
            except Exception:
                pass  # некритично — продолжаем с текущей ролью
        # Стиль из внешних фидов (только как подсказка тона), если включено.
        # В реальном EventLoop.run_cycle нет отдельного параметра style_hint —
        # подмешиваем как инструкцию в начало сообщения (как в ТЗ «подсказка стиля»).
        style_hint = ""
        if cfg.context.enabled and cfg.context.injection_rate > 0:
            try:
                style_hint = _run_async(
                    self._get_feed().fetch_style_hints(cfg.context.injection_rate)
                )
            except Exception:
                style_hint = ""
        effective_input = (style_hint + "\n" + text) if style_hint else text
        try:
            # run_cycle сам озвучивает ответ через Silero (внутренний _speak),
            # поэтому двойного проговаривания не делаем; audio_url не формируем.
            reply = _run_async(
                asyncio.wait_for(agent.event_loop.run_cycle(effective_input), timeout=90.0)
            )
            if reply is None:
                reply = ""
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        # 🤖 Универсальный UI-движок: оборачиваем ответ в ui_events (generic, без сценариев).
        # Классификация ТОЛЬКО на бэкенде (фронт не решает по ключевым словам — ADR/Директива).
        import uuid as _uuid
        task_id = "task_" + _uuid.uuid4().hex[:8]
        # простая эвристика: многострочный/маркированный ответ -> result_list, иначе result_text
        _lines = [ln.strip("•- \t") for ln in reply.splitlines() if ln.strip()]
        _looks_list = len(_lines) >= 2 and (
            "\n" in reply or reply.count("•") >= 2
            or (reply.count("-") >= 2 and len(reply) > 40)
        )
        if _looks_list:
            _component = "result_list"
            _ui = {
                "component": _component,
                "items": [{"title": ln, "description": ln} for ln in _lines[:12]],
            }
        else:
            _component = "result_text"
            _ui = {"component": _component, "text": reply}
        events = [
            {"type": "task.started", "task_id": task_id, "mode": "quick",
             "title": (text[:60] or "Задача")},
            {"type": "task.done", "task_id": task_id, "title": "Готово",
             "message": reply[:140], "ui": _ui},
        ]
        # 🤖 U-04: серверная валидация — белый список типов, очистка src/actions.
        # Невалидный компонент -> честный текстовый пузырь (validate_component
        # сводит к result_text), мёртвых кнопок нет (actions только из карты).
        events = validate_ui_events(events)
        if not events:
            events = [{"type": "task.done", "task_id": task_id,
                       "title": "Готово", "message": reply[:140]}]
        _UI_TASKS[task_id] = events
        self._json(200, {
            "text": reply,
            "audio_url": None,
            "style_hint": style_hint,
            "task_id": task_id,
            "ui_events": events,
        })

    def _handle_camera_start(self, body: dict) -> None:
        agent = self._get_chat_agent()
        camera = agent.capabilities.get("camera")
        if camera is None:
            self._json(404, {"error": "camera capability unavailable"})
            return
        try:
            res = _run_async(camera.start(notice_ack=True))
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if not getattr(res, "success", False):
            self._json(409, {"error": getattr(res, "message", "camera start failed")})
            return
        self._json(200, {"ok": True, "started": True})

    def _handle_camera_stop(self) -> None:
        agent = self._get_chat_agent()
        camera = agent.capabilities.get("camera")
        if camera is None:
            self._json(404, {"error": "camera capability unavailable"})
            return
        try:
            _run_async(camera.stop())
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._json(200, {"ok": True})

    def _handle_vision_capture(self, body: dict | None = None) -> None:
        """Capture a screen frame for the LLM/vision pipeline.

        🤖 Ground-truth (vision contract): Desktop Companion sends a desktop
        screenshot as base64 in the request body (``image_b64``). We accept that
        directly — it is fast, needs no camera, and never blocks. The legacy
        web-camera path (``CameraCapability.capture_base64_frame``) is kept only
        as an explicit opt-in fallback when the body carries no image and a
        camera capability is available.

        Response: {"image_b64": "<data url>"} on success, or a 4xx/5xx error
        with a clear message. Always answers quickly (no hang on missing cam).
        """
        # 1) Desktop screenshot supplied by the companion (preferred, no camera).
        if isinstance(body, dict):
            raw = body.get("image_b64")
            if isinstance(raw, str) and raw.strip():
                b64 = raw.strip()
                # Accept either a raw base64 blob or a data: URL.
                if "," in b64 and b64.startswith("data:"):
                    header, payload = b64.split(",", 1)
                    if not _is_valid_base64(payload):
                        self._json(400, {"error": "image_b64: невалидный base64 в data URL"})
                        return
                    image_b64 = b64
                else:
                    if not _is_valid_base64(b64):
                        self._json(400, {"error": "image_b64: невалидный base64"})
                        return
                    # Normalize to a data URL for downstream consumers.
                    image_b64 = "data:image/png;base64," + b64
                if len(image_b64) > 15_000_000:  # ~10MB image guard
                    self._json(413, {"error": "image_b64 слишком большой (>10MB)"})
                    return
                self._json(200, {"image_b64": image_b64, "source": "desktop"})
                return

        # 2) Legacy fallback: web camera (opt-in, may be unavailable).
        agent = self._get_chat_agent()
        camera = agent.capabilities.get("camera") if agent is not None else None
        if camera is None:
            self._json(409, {"error": "нет image_b64 в теле и camera capability недоступен"})
            return
        try:
            res = _run_async(camera.capture_base64_frame())
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        finally:
            try:
                _run_async(camera.stop())
            except Exception:
                pass
        if not getattr(res, "success", False):
            self._json(409, {"error": getattr(res, "message", "capture failed")})
            return
        self._json(200, {"image_b64": (res.data or {}).get("image_b64"), "source": "camera"})

    def _handle_safety_post(self, body: dict) -> None:
        agent = self._get_chat_agent()
        guard = getattr(agent, "guard", None)
        if guard is None:
            self._json(503, {"error": "guard недоступен (агент не инициализирован)"})
            return
        cfg = guard.cfg
        level = body.get("autonomy_level")
        if level in ("off", "observe", "suggest", "act"):
            cfg.autonomy_level = level
            ctrl = getattr(agent, "autonomous", None)
            if ctrl is not None:
                if level == "off":
                    try:
                        _run_async(ctrl.stop())
                    except Exception:
                        pass
                elif not getattr(ctrl, "_tasks", set()):
                    try:
                        _run_async(ctrl.start())
                    except Exception:
                        pass
        self._json(200, {"ok": True})

    def _handle_xtoys(self) -> None:
        """Управление XToys-устройством через существующий capability.

        NOTE: адаптировано под реальный XToysCapability (нет vibe/stop/pattern —
        есть set_intensity / select_pattern). Кламп max_intensity снят (п.4 ТЗ:
        «как попросили — так и шлём»); физический предел устройства — за пультом.
        """
        try:
            data = self._read_json_body()
            # принимаем command ИЛИ action (обратно совместимо с фронтендом)
            cmd = (data.get("command") or data.get("action") or "").strip().lower()
            agent = self._get_chat_agent()
            xtoys = agent.capabilities.get("xtoys")
            if xtoys is None:
                # Emulated mode: физическое устройство не подключено. Пользователь
                # управляет им через реальный пульт — поэтому просто подтверждаем
                # команду локально (безопасно, без сетевых вызовов к устройству).
                self._json(200, {
                    "ok": True,
                    "mode": "emulated",
                    "command": cmd,
                    "message": f"emulated: {cmd} принято (устройство не подключено — управление за физическим пультом)",
                })
                return
            if cmd in ("oscillate",):
                duration = int(data.get("duration", 2000))
                intensity = float(data.get("intensity", 0.5))
            elif cmd in ("set_intensity", "intensity"):
                # фронтенд шлёт intensity в процентах (0..100)
                pct = max(0, min(100, int(round(float(data.get("intensity", 0))))))
                res = _run_async(xtoys.set_intensity("", pct))
                self._json(200, {"ok": bool(getattr(res, "success", False)),
                                 "message": f"intensity {pct}%"})
                return
            elif cmd == "stop":
                res = _run_async(xtoys.set_intensity("", 0))
                self._json(200, {"ok": bool(getattr(res, "success", False)), "message": "stopped"})
                return
            elif cmd == "macro":
                # intensity 0..1 -> процент; для плавного разгона используем ramp.
                pct = max(0, min(100, int(round(intensity * 100))))
                res = _run_async(xtoys.ramp_intensity("", pct, steps=max(1, int(duration / 400))))
                self._json(200, {"ok": bool(getattr(res, "success", False)),
                                 "message": f"oscillate {duration}ms @ {pct}%"})
            elif cmd == "stop":
                res = _run_async(xtoys.set_intensity("", 0))
                self._json(200, {"ok": bool(getattr(res, "success", False)), "message": "stopped"})
            elif cmd == "macro":
                name = str(data.get("name", ""))
                allowed = {"ramp", "climb", "pulse", "wave", "hold", "cooldown"}
                if name in allowed:
                    res = _run_async(xtoys.select_pattern(name))
                    self._json(200, {"ok": bool(getattr(res, "success", False)), "message": f"macro {name}"})
                else:
                    self._json(400, {"error": f"unknown macro: {name}"})
            else:
                self._json(400, {"error": f"unknown command: {cmd}"})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc)})

    def _handle_context_feed_get(self) -> None:
        cfg = load_config()
        self._json(200, {
            "enabled": cfg.context.enabled,
            "allow_external_scrape": cfg.context.allow_external_scrape,
            "injection_rate": cfg.context.injection_rate,
            "tonal_mode": cfg.context.tonal_mode,
            "feeds": self._get_feed().list_feeds(),
        })

    def _handle_context_feed_post(self, body: dict) -> None:
        feed = self._get_feed()
        if isinstance(body.get("add"), str):
            feed.add_feed_url(body["add"])
        if isinstance(body.get("remove"), str):
            feed.remove_feed_url(body["remove"])
        if isinstance(body.get("hints"), list):
            feed.cache_local_hints([str(h) for h in body["hints"]])
        cfg = load_config()
        if "enabled" in body:
            cfg.context.enabled = bool(body["enabled"])
        if "injection_rate" in body:
            try:
                cfg.context.injection_rate = max(0.0, min(1.0, float(body["injection_rate"])))
            except (TypeError, ValueError):
                pass
        if "tonal_mode" in body:
            cfg.context.tonal_mode = str(body["tonal_mode"])
        if "allow_external_scrape" in body:
            cfg.context.allow_external_scrape = bool(body["allow_external_scrape"])
            feed.set_external_scrape(cfg.context.allow_external_scrape)
        self._handle_context_feed_get()

    def _save_config(self, payload: dict) -> None:
        """Persist council settings (and endpoint keys) into the local config.yaml.

        Only known council fields are written; secrets (api_key) are stored as-is from
        the UI. The file is local-only and git-ignored (see .gitignore).
        """
        cfg = load_config()
        c = cfg.council
        if "browser_enabled" in payload:
            c.browser_enabled = bool(payload["browser_enabled"])
        if "free_tier_only" in payload:
            c.free_tier_only = bool(payload["free_tier_only"])
        if "min_interval_seconds" in payload:
            try:
                c.min_interval_seconds = max(0.5, float(payload["min_interval_seconds"]))
            except (TypeError, ValueError):
                pass
        if "timeout_seconds" in payload:
            try:
                c.timeout_seconds = max(5.0, float(payload["timeout_seconds"]))
            except (TypeError, ValueError):
                pass
        if "concurrency" in payload:
            try:
                c.concurrency = max(1, min(8, int(payload["concurrency"])))
            except (TypeError, ValueError):
                pass
        # Autonomous flags (UI mirror of config.autonomous.*)
        if "autonomous_enabled" in payload:
            cfg.autonomous.enabled = bool(payload["autonomous_enabled"])
        if "auto_start_session" in payload:
            cfg.autonomous.auto_start_session = bool(payload["auto_start_session"])
        _SECRET_PARAM_RE = re.compile(r"[?&](api_key|key|token|secret|access_token|authorization)=", re.IGNORECASE)
        for name, ep in (payload.get("endpoints") or {}).items():
            if name not in c.api_endpoints or not isinstance(ep, dict):
                continue
            if "base_url" in ep:
                base_url = str(ep["base_url"]).strip()
                # SECURITY: never persist a secret embedded in the Base URL query string.
                if _SECRET_PARAM_RE.search(base_url):
                    raise ValueError(
                        f"Base URL для {name} содержит секрет в параметрах запроса. "
                        f"Используйте отдельное поле API key, а не query-параметры."
                    )
                if len(base_url) > 500 or (base_url and urlparse(base_url).scheme not in {"http", "https"}):
                    raise ValueError(f"invalid base URL for {name}")
                c.api_endpoints[name]["base_url"] = base_url
            if "api_key" in ep and ep["api_key"]:
                # Only overwrite when the user typed a new key (not the masked placeholder).
                api_key = str(ep["api_key"]).strip()
                if len(api_key) > 4096:
                    raise ValueError(f"API key for {name} is too long")
                c.api_endpoints[name]["api_key"] = api_key
        # Round-trip through a clean dict so pydantic secrets are written plainly.
        data = cfg.model_dump()
        import yaml

        with (_ROOT / "config.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

def _delete_history(round_id: str) -> int:
    """Delete one round's artifacts, or all when round_id == '__all__'."""
    directory = (_ROOT / load_config().council.artifacts_dir).resolve()
    if not directory.exists():
        return 0
    if round_id == "__all__":
        files = list(directory.glob("*_report.md")) + list(directory.glob("*_meta.json")) + \
                list(directory.glob("*_*.md"))
        for f in files:
            try:
                f.unlink()
            except OSError:
                pass
        return len(files)
    count = 0
    for pat in (f"{round_id}_report.md", f"{round_id}_meta.json", f"{round_id}_*.md"):
        for f in directory.glob(pat):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
    return count


class _RemoteGatewayHandler(_Handler):
    """Public surface restricted to the token-protected Remote room."""

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/remote-control", "/remote-control.html"):
            page = _HERE / "remote-control.html"
            if page.is_file():
                self._send_file_with_cache(page, "text/html; charset=utf-8", no_cache=True)
            else:
                self._send(404, b"remote controller missing", "text/plain")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        if path in {
            "/api/xtoys/remote/control",
            "/api/xtoys/remote/heartbeat",
            "/api/xtoys/remote/room",
        }:
            self.path = path
            return super().do_POST()
        self._send(404, b"not found", "text/plain")


def run_webui(host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}/"
    print("=" * 64)
    print("  UNI · консоль разработки (WebUI)")
    print(f"  Открой: {url}")
    print("  Ctrl+C — остановить")
    print("=" * 64, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[webui] остановлена.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_webui(port=int(os.environ.get("UNI_WEBUI_PORT", _DEFAULT_PORT)))
