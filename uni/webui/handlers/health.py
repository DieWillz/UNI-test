"""Агрегатор здоровья всех компонентов Юни (P-13, 2026-08-17).

GET /api/uni/health — единый endpoint для мониторинга/healthcheck.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import registry

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]


def _tcp_alive(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}"], stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False


def _memory_status() -> dict[str, Any]:
    status: dict[str, Any] = {
        "facts_count": 0, "dialogue_turns": 0,
        "trajectories_ok": True, "fake_quarantined": False,
    }
    working = _ROOT / "memory" / "working.json"
    if working.is_file():
        try:
            data = json.loads(working.read_text(encoding="utf-8", errors="replace"))
            status["facts_count"] = len(data.get("facts") or {})
            status["dialogue_turns"] = len(data.get("dialogue") or [])
        except (json.JSONDecodeError, OSError):
            pass
    traj = _ROOT / "uni" / "memory" / "trajectories.jsonl"
    fake = _ROOT / "uni" / "memory" / "trajectories.jsonl.FAKE"
    status["fake_quarantined"] = fake.is_file()
    if traj.is_file():
        try:
            coords: list[tuple[int, int]] = []
            with open(traj, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        rec = json.loads(line)
                        for step in rec.get("steps") or []:
                            if isinstance(step, dict):
                                x, y = step.get("x"), step.get("y")
                                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                                    coords.append((int(x), int(y)))
                    except json.JSONDecodeError:
                        continue
            if len(coords) >= 10:
                from collections import Counter
                top_freq = Counter(coords).most_common(1)[0][1]
                if top_freq / len(coords) > 0.5:
                    status["trajectories_ok"] = False
        except OSError:
            pass
    return status


def _config_status() -> dict[str, Any]:
    import os
    status: dict[str, Any] = {"valid": True, "secrets_masked": True, "env_overrides": []}
    if not (_ROOT / "config.yaml").is_file():
        status["valid"] = False
        return status
    try:
        from uni.config import load_config
        load_config(str(_ROOT / "config.yaml"))
    except Exception:
        status["valid"] = False
    for k in sorted(os.environ):
        if k.startswith("UNI_") and any(n in k.lower() for n in ("secret", "key", "token", "password")):
            status["env_overrides"].append(k)
    return status


def _handle_health(handler) -> None:
    pids: dict[str, Any] = {}
    try:
        pids = json.loads((_ROOT / "runtime" / "pids.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    ports = (1235, 8787, 1236, 7860, 1234)
    # Probe independent localhost services concurrently. Sequential one-second
    # connect timeouts made the health endpoint exceed client deadlines when
    # all optional services were offline.
    with ThreadPoolExecutor(max_workers=len(ports), thread_name_prefix="uni-health") as pool:
        states = dict(zip(ports, pool.map(lambda port: _tcp_alive("127.0.0.1", port), ports)))
    llama_running = states[1235]
    webui_running = states[8787]
    vlm_running = states[1236]
    moondream_running = states[7860]
    lmstudio_reachable = states[1234]

    llama_model = None
    if llama_running:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:1235/v1/models", timeout=2) as r:
                m = json.loads(r.read().decode("utf-8"))
                if m.get("data"):
                    llama_model = m["data"][0].get("id")
        except Exception:
            pass

    lmstudio_models: list[str] = []
    if lmstudio_reachable:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=2) as r:
                lmstudio_models = [str(x.get("id")) for x in json.loads(r.read().decode("utf-8")).get("data", []) if x.get("id")]
        except Exception:
            pass

    audio: dict[str, Any] = {"stt": "НЕ ПРОВЕРЕНО", "tts": "НЕ ПРОВЕРЕНО", "warnings": [], "notices": []}
    try:
        from uni.utils.audio_env_detect import detect_audio_environment
        env = detect_audio_environment()
        audio["warnings"] = env.get("warnings", [])
        audio["notices"] = env.get("notices", [])
        if env.get("available"):
            audio["stt"] = "микрофон есть"; audio["tts"] = "вывод есть"
        else:
            audio["stt"] = "STT отключён"; audio["tts"] = "вывод отключён"
    except Exception as e:
        audio["stt"] = "STT отключён"; audio["tts"] = "вывод отключён"
        audio["notices"] = [f"audio_env_detect недоступен: {e}"]

    memory = _memory_status()
    config = _config_status()
    electron_pid = (pids.get("electron") or {}).get("pid")

    components = {
        "llama": {"running": llama_running, "port": 1235, "model": llama_model, "pid": (pids.get("llama") or {}).get("pid")},
        "webui": {"running": webui_running, "port": 8787, "pid": (pids.get("webui") or {}).get("pid")},
        "electron": {"running": _pid_alive(electron_pid), "pid": electron_pid},
        "vlm_local": {"running": vlm_running, "port": 1236},
        "moondream": {"running": moondream_running, "port": 7860},
        "lmstudio": {"reachable": lmstudio_reachable, "model_loaded": bool(lmstudio_models), "models": lmstudio_models},
        "audio": audio, "memory": memory, "config": config,
    }
    critical_ok = llama_running and webui_running and memory.get("trajectories_ok", True)
    handler._json(200, {
        "ok": critical_ok, "ts": time.time(), "components": components,
        "summary": "Юни готова" if critical_ok else "Есть проблемы — см. components",
    })


registry.register("GET", "/api/uni/health", _handle_health, "агрегатор здоровья всех компонентов")
