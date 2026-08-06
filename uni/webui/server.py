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
import json
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from uni.config import load_config
from uni.council.participants import load_participants
from uni.council.round import CouncilRound

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_FRONTEND = _HERE / "index.html"


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

# ===== Состояние чат-хаба (мультимодальный режим) =====
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



# Kept deliberately small: the WebUI ships only a handful of asset types. Anything
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
        self.wfile.write(body)

    def _json(self, code: int, value: Any) -> None:
        self._send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"))

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
        if parsed.path in ("/favicon.ico",):
            # B-04: заглушка, чтобы не было 404 в консоли браузера
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

        if parsed.path in ("/api/context/feed", "/api/context/feed/"):
            self._handle_context_feed_get()
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
        # B-02: SPA fallback — любой non-API путь (например, deep-link вкладки)
        # отдаёт index.html, чтобы фронтенд восстановил состояние из location.hash.
        if parsed.path and not parsed.path.startswith("/api/"):
            if _FRONTEND.exists():
                self._send_file_with_cache(_FRONTEND, "text/html; charset=utf-8", no_cache=True)
                return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
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
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    line = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                    self.wfile.flush()
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
        if self.path == "/api/camera/start":
            self._handle_camera_start(self._read_json_body())
            return
        if self.path == "/api/camera/stop":
            self._handle_camera_stop()
            return
        if self.path == "/api/vision/capture":
            self._handle_vision_capture()
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
                from uni.roles.loader import set_current_role

                set_current_role(name)
                agent = self._get_chat_agent()
                loaded = False
                if agent is not None:
                    loaded = agent.event_loop._load_role_prompt(name)
                self._json(200, {"ok": True, "role": name, "prompt_loaded": loaded})
            except Exception as exc:
                self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
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
            except Exception as exc:  # агент без тяжёлых capability отвечает текстом
                agent._init_error = f"{type(exc).__name__}: {exc}"
                init_error["err"] = agent._init_error
            # loop остаётся живым для последующих _run_async вызовов

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
        text = (body.get("text") or "").strip()
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
        self._json(200, {"text": reply, "audio_url": None, "style_hint": style_hint})

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
        self._json(200, {"ok": True, "started": bool(getattr(res, "success", False))})

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

    def _handle_vision_capture(self) -> None:
        agent = self._get_chat_agent()
        camera = agent.capabilities.get("camera")
        if camera is None:
            self._json(404, {"error": "camera capability unavailable"})
            return
        try:
            res = _run_async(camera.capture_atomic())
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        if not getattr(res, "success", False):
            self._json(409, {"error": getattr(res, "message", "capture failed")})
            return
        self._json(200, {"image_b64": (res.data or {}).get("image_b64")})

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
            cmd = data.get("command")
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
            if cmd == "oscillate":
                duration = int(data.get("duration", 2000))
                intensity = float(data.get("intensity", 0.5))
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
                allowed = {"pulse", "wave", "tease", "punish"}
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
    run_webui()
