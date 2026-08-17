"""uni/webui/admin_api.py — Админка полного контроля (Директива ADM-01, 2026-08-13).

Отдельный модуль (НЕ раздувает server.py). Чистые функции возвращают dict
для эндпоинтов /api/admin/*. Все функции fail-closed: при ошибке/нет данных
возвращают честный «—» / «нет данных», НЕ крашат и НЕ отдают секреты
(запрет на config.yaml/токены/ключи — см. _safe_*).

ЗАПРЕТ: ни одна функция не возвращает содержимое config.yaml, ключей, токенов.
Бинд только 127.0.0.1 (проверяется в server.py при маршрутизации).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Пути относительно корня проекта (uni/webui/ -> ../../)
_HERE = Path(__file__).resolve().parent          # uni/webui
_ROOT = _HERE.parent.parent                       # C:\LLM\UNI
_RUNTIME = _ROOT / "runtime"
_BRIDGE = _ROOT / "agents" / "bridge"            # исправлено: bridge/ лежит в agents/
_OUTBOX = _ROOT / "agents" / "outbox"            # исправлено: outbox/ лежит в agents/

# Таймауты сетевых проверок (сек)
_TCP_TIMEOUT = 1.5


def _tcp_alive(host: str, port: int) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT):
            return True
    except OSError:
        return False


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _pids() -> dict:
    return _read_json(_RUNTIME / "pids.json", {}) or {}


# ────────────────────────────────────────────────────────────
# /api/admin/stack — llama/webui/launcher/electron + модель
# ────────────────────────────────────────────────────────────
def admin_stack() -> dict:
    pids = _pids()
    out: dict[str, Any] = {}

    # llama :1235 + имя модели
    llama_pid = (pids.get("llama") or {}).get("pid")
    llama_up = _tcp_alive("127.0.0.1", 1235)
    model = None
    if llama_up:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:1235/v1/models", timeout=2) as r:
                m = json.loads(r.read().decode("utf-8"))
                if m.get("data"):
                    model = m["data"][0].get("id")
        except Exception:
            pass
    out["llama"] = {"pid": llama_pid, "port": 1235, "running": llama_up, "model": model}

    # webui :8787
    webui_pid = (pids.get("webui") or {}).get("pid")
    out["webui"] = {"pid": webui_pid, "port": 8787, "running": _tcp_alive("127.0.0.1", 8787)}

    # launcher (если есть pid)
    launcher_pid = (pids.get("launcher") or {}).get("pid")
    out["launcher"] = {"pid": launcher_pid, "running": bool(launcher_pid)}

    # electron (desktop)
    electron_pid = (pids.get("electron") or {}).get("pid")
    out["electron"] = {"pid": electron_pid, "running": bool(electron_pid)}

    return out


# ────────────────────────────────────────────────────────────
# /api/admin/hw — GPU/RAM/CPU (честно, нет данных -> «—»)
# ────────────────────────────────────────────────────────────
def admin_hw() -> dict:
    hw: dict[str, Any] = {"gpu": {"vram_free": "—", "vram_used": "—", "utilization": "—"},
                          "ram": "—", "cpu": "—"}
    # GPU через nvidia-smi (если есть)
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if res.returncode == 0 and res.stdout.strip():
            free, used, util = [x.strip() for x in res.stdout.strip().split(",")]
            hw["gpu"] = {"vram_free": f"{free} MiB", "vram_used": f"{used} MiB",
                         "utilization": f"{util} %"}
    except Exception:
        pass  # нет nvidia-smi -> «—»
    # RAM/CPU через psutil (если есть), иначе «—»
    try:
        import psutil
        vm = psutil.virtual_memory()
        hw["ram"] = f"{vm.used // (1024**2)} / {vm.total // (1024**2)} MB"
        hw["cpu"] = f"{psutil.cpu_percent(interval=0.3):.0f} %"
    except Exception:
        pass
    return hw


# ────────────────────────────────────────────────────────────
# /api/admin/git — ветка, последний коммит (нет git -> «—»)
# ────────────────────────────────────────────────────────────
def admin_git() -> dict:
    g: dict[str, Any] = {"branch": "—", "commit": "—", "message": "—", "time": "—"}
    try:
        branch = subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=5)
        if branch.returncode == 0:
            g["branch"] = branch.stdout.strip()
        last = subprocess.run(["git", "-C", str(_ROOT), "log", "-1", "--format=%H|%s|%cr"],
                              capture_output=True, text=True, timeout=5)
        if last.returncode == 0 and last.stdout.strip():
            h, msg, when = last.stdout.strip().split("|", 2)
            g["commit"], g["message"], g["time"] = h[:10], msg, when
    except Exception:
        pass
    return g


# ────────────────────────────────────────────────────────────
# /api/admin/dev — фазы/задачи/backlog/locks
# ────────────────────────────────────────────────────────────
def _phases() -> list[dict]:
    data = _read_json(_RUNTIME / "admin" / "phases.json", [])
    if isinstance(data, dict):  # поддержка {phases: [...]} и [...]
        data = data.get("phases", [])
    return data if isinstance(data, list) else []


def _backlog_items() -> list[dict]:
    p = _ROOT / "UNI_BACKLOG.md"
    items = []
    if not p.is_file():
        return items
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("## ") and not s.startswith("- ["):
            continue
        status = "—"
        if "[V]" in s or "[x]" in s:
            status = "DONE"
        elif "[ ]" in s:
            status = "IN PROGRESS" if "IN PROGRESS" in s else "BLOCKED" if "BLOCKED" in s else "TODO"
        items.append({"raw": s.lstrip("#- "), "status": status})
    return items


def admin_dev() -> dict:
    locks = _read_json(_ROOT / "UNI_LOCKS.json", {}) or {}
    try:
        backlog_text = (_ROOT / "UNI_BACKLOG.md").read_text(encoding="utf-8") if (_ROOT / "UNI_BACKLOG.md").is_file() else "нет данных"
    except Exception:
        backlog_text = "нет данных"
    return {
        "phases": _phases(),
        "backlog": _backlog_items(),
        "backlog_md": backlog_text,
        "locks": locks,
    }


# ────────────────────────────────────────────────────────────
# /api/admin/agents — heartbeats всех ИИ
# ────────────────────────────────────────────────────────────
def _parse_heartbeat(path: Path, name: str) -> dict:
    info = {"name": name, "alive": False, "minutes_since": None, "last_line": None}
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not text:
            return info
        last = text[-1].strip()
        info["last_line"] = last[:200]
        # формат: "2026-08-13 16:35 UTC+3 — ..."
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", last)
        if m:
            try:
                from datetime import datetime
                ts = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
                age = (datetime.now() - ts).total_seconds() / 60.0
                info["minutes_since"] = round(age, 1)
                info["alive"] = age <= 15  # жив, если биение <=15 мин назад
            except Exception:
                pass
    except Exception:
        pass
    return info


def admin_agents() -> dict:
    agents = []
    # agents/bridge/heartbeat_*.txt
    for p in sorted(_BRIDGE.glob("heartbeat_*.txt")):
        agents.append(_parse_heartbeat(p, p.name))
    # agents/uni-*/logs/heartbeat*.txt (ИИ-песочницы)
    for p in sorted((_ROOT / "agents").glob("uni-*/logs/heartbeat*.txt")):
        agents.append(_parse_heartbeat(p, p.name))
    return {"agents": agents, "count": len(agents)}


# ────────────────────────────────────────────────────────────
# /api/admin/stats — счётчики из UNI_JOURNAL.jsonl + pytest
# ────────────────────────────────────────────────────────────
def admin_stats() -> dict:
    stats: dict[str, Any] = {
        "ui_events_by_component": {},
        "stop_count": 0,
        "demo_mouse_count": 0,
        "vision_capture_count": 0,
        "chat_messages": 0,
        "pytest": "нет данных",
    }
    journal = _ROOT / "UNI_JOURNAL.jsonl"
    if journal.is_file():
        try:
            for line in journal.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                etype = rec.get("event") or rec.get("type")
                comp = rec.get("component") or rec.get("ui", {}).get("component") if isinstance(rec.get("ui"), dict) else rec.get("component")
                if etype == "ui_event" and comp:
                    stats["ui_events_by_component"][comp] = stats["ui_events_by_component"].get(comp, 0) + 1
                elif etype in ("stop", "stop_cycle"):
                    stats["stop_count"] += 1
                elif etype == "demo_mouse":
                    stats["demo_mouse_count"] += 1
                elif etype in ("vision_capture", "vision_capture_done"):
                    stats["vision_capture_count"] += 1
                elif etype in ("chat", "chat_message", "user_message"):
                    stats["chat_messages"] += 1
        except Exception:
            pass
    # последний pytest
    pt = _read_json(_RUNTIME / "pytest_last.json")
    if pt:
        stats["pytest"] = pt
    else:
        xml = _OUTBOX / "HERMES_PYTEST.xml"
        if xml.is_file():
            stats["pytest"] = "есть HERMES_PYTEST.xml (детали в outbox)"
        else:
            stats["pytest"] = "нет данных"
    return stats


# ────────────────────────────────────────────────────────────
# /api/admin/reports — список + содержимое отчётов
# ────────────────────────────────────────────────────────────
def admin_reports_list() -> dict:
    reps = []
    for p in sorted(_OUTBOX.glob("*.md")):
        reps.append({"name": p.name, "kind": "outbox"})
    for p in sorted(_BRIDGE.glob("REPORT_*")):
        reps.append({"name": p.name, "kind": "bridge"})
    # 🤖 Hermes (2026-08-14): добавлен скан отчётов Hermes из
    # agents/uni-codex/outbox (там лежат REPORT_*/DIRECTIVE_*/ANALYSIS_*).
    _HERMES_OUTBOX = _ROOT / "agents" / "uni-codex" / "outbox"
    if _HERMES_OUTBOX.is_dir():
        for p in sorted(_HERMES_OUTBOX.glob("*.md")):
            reps.append({"name": p.name, "kind": "hermes-outbox"})
    if not reps:
        return {"reports": [{"name": "нет данных", "kind": "—"}]}
    return {"reports": reps}


def admin_report_content(name: str) -> dict:
    # 🤖 ЗАПРЕТ: блокируем попытки выйти за пределы папок (path traversal)
    name = os.path.basename(name)
    if not name or name in (".", ".."):
        return {"error": "bad name"}
    # 🤖 Hermes (2026-08-14): добавлен базовый путь agents/uni-codex/outbox
    _HERMES_OUTBOX = _ROOT / "agents" / "uni-codex" / "outbox"
    for base in (_OUTBOX, _BRIDGE, _HERMES_OUTBOX):
        cand = (base / name)
        try:
            if cand.resolve().is_relative_to(base.resolve()) and cand.is_file():
                return {"name": name, "content": cand.read_text(encoding="utf-8", errors="replace")}
        except Exception:
            continue
    return {"error": "not found"}


# ────────────────────────────────────────────────────────────
# POST /api/admin/actions — белый список (ADM-02)
# Возвращает dict результата; любая ошибка -> исключение (ловится в server.py).
# ────────────────────────────────────────────────────────────
_STATE_PATH = _HERE.parent / "desktop" / "state.json"   # uni/desktop/state.json


def _write_state(key: str, value: Any) -> dict:
    data = _read_json(_STATE_PATH, {}) or {}
    data[key] = value
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"key": key, "value": value, "state_path": str(_STATE_PATH)}


def _run_background(cmd: list[str], out_json_key: str) -> dict:
    """Запустить команду в фоне, записать старт в runtime/<out_json_key>_last.json."""
    log_path = _RUNTIME / f"{out_json_key}_last.json"
    try:
        _RUNTIME.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        log_path.write_text(json.dumps({
            "status": "running", "pid": proc.pid, "cmd": " ".join(cmd),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "started", "pid": proc.pid}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _handle_admin_action(action: str, params: dict) -> dict:
    if action == "stop_stack":
        # убить весь стек по pids.json (как /api/admin/stop)
        pids = _read_json(_RUNTIME / "pids.json", {}) or {}
        killed = []
        for key in ("llama", "webui", "electron"):
            pid = (pids.get(key) or {}).get("pid")
            if pid:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                    killed.append(key)
                except Exception:
                    pass
        try:
            (_RUNTIME / "pids.json").unlink(missing_ok=True)
        except Exception:
            pass
        return {"killed": killed}

    if action == "restart_webui":
        # мягкий рестарт: убить webui, лаунчер поднимет снова (если есть launcher)
        pid = (pids := _read_json(_RUNTIME / "pids.json", {}) or {}).get("webui", {}).get("pid")
        if pid:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                return {"restarted": "webui", "pid": pid}
            except Exception as e:
                return {"error": str(e)}
        return {"note": "webui pid не найден в pids.json"}

    if action == "run_pytest":
        # фоновый pytest через _pytest_runner, который пишет результат в
        # runtime/pytest_last.json (читается admin_stats для ADM-10).
        py = os.environ.get("PYTHON", sys.executable)
        runner = str(_HERE / "_pytest_runner.py")
        return _run_background([py, runner], "pytest")

    if action == "run_selftest":
        try:
            from uni.tools.selftest import run_all, save_report, render_markdown
            checks = run_all()
            p = save_report(checks)
            return {"report_path": str(p), "checks": checks, "markdown": render_markdown(checks)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if action == "run_arch_check":
        # лёгкая проверка: py_compile всех uni/*.py
        import compileall
        ok = compileall.compile_dir(str(_HERE.parent), quiet=1, max_depth=6)
        return {"compile_ok": bool(ok)}

    if action == "create_stop_txt":
        stop = _ROOT / "STOP.txt"
        stop.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + " STOP от админки\n", encoding="utf-8")
        return {"created": str(stop)}

    if action == "set_ui_variant":
        return _write_state("interface", str(params.get("v", "v4")))

    if action == "set_role":
        return _write_state("role", str(params.get("r", "default")))

    if action == "set_consent":
        lvl = str(params.get("L", "L0"))
        if not lvl.startswith("L") or not lvl[1:].isdigit():
            raise ValueError("consent должен быть L0..L4")
        return _write_state("consent", lvl)

    if action == "set_autostart":
        return _write_state("autostart", bool(params.get("on", True)))

    if action == "set_opacity":
        return _write_state("opacity", str(params.get("opacity", "0.95")))

    if action == "demo_mouse":
        try:
            # The canonical implementation lives in routers_desktop and uses
            # capabilities.human_mouse.  There is no separate capabilities.mouse
            # module; importing that old path made the admin action fail silently.
            from .routers_desktop import mouse_demo
            return mouse_demo()
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if action == "vision_capture":
        # 🤖 Qwen (2026-08-16): скриншоты пишутся в agents/outbox/ (существует),
        # а не в несуществующую папку. Путь уже исправлен выше (_OUTBOX).
        out = _OUTBOX / f"admin_capture_{int(time.time())}.png"
        try:
            import pyautogui
            pyautogui.screenshot(str(out))
            return {"path": str(out)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if action == "show_overlay":
        # показать оверлей: убрать minimized/скрытость через скрипт лаунчера
        return {"note": "overlay show — требует electron; см. лаунчер"}

    if action == "run_packaging":
        # старт фазы 9 (упаковка): запустить build_dist.bat в фоне
        bat = _ROOT / "build_dist.bat"
        if bat.is_file():
            return _run_background([str(bat)], "packaging")
        return {"note": "build_dist.bat не найден"}

    raise ValueError(f"unknown action: {action}")

