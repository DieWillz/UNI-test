"""
audio_env_detect.py — АДАПТИРОВАННАЯ ВЫЖИМКА из Hermes tools/voice_mode.py
(detect_audio_environment) для проекта Юни (C:\\LLM\\UNI\\uni).

Источник: hermes-agent/tools/voice_mode.py (2308 строк, © Hermes Agent).
Взято: детект окружения, где аудио НЕ работает (SSH/Docker/WSL/Termux),
чтобы Юни честно сообщала «микрофон недоступен» вместо тихого падения.

Очищено от hermes_constants/is_container/is_termux — заменено на
самостоятельные проверки (env-переменные, /proc/version). Без зависимостей Hermes.
"""


import os
import socket
import stat


def is_container() -> bool:
    try:
        with open("/.dockerenv", "r", encoding="utf-8"):
            return True
    except OSError:
        pass
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except OSError:
        return False


def is_wsl() -> bool:
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def is_ssh() -> bool:
    return any(
        os.environ.get(v) for v in ("SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION")
    )


def has_forwarded_audio() -> bool:
    """Есть ли проброшенный звуковой сервер (PulseAudio/PipeWire socket)."""
    import os
    import socket
    import stat

    candidates = []
    pulse = os.environ.get("PULSE_SERVER", "")
    for part in pulse.split(";"):
        part = part.strip()
        if part.startswith("unix:"):
            candidates.append(part[len("unix:"):])
    prt = os.environ.get("PULSE_RUNTIME_PATH")
    if prt:
        candidates.append(f"{prt}/native")
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        candidates.append(f"{xdg}/pulse/native")
        candidates.append(f"{xdg}/pipewire-0")
    for path in candidates:
        if not path:
            continue
        try:
            if not stat.S_ISSOCK(os.stat(path).st_mode):
                continue
        except OSError:
            continue
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)
            sock.connect(path)
            return True
        except OSError:
            continue
        finally:
            sock.close()
    return bool(os.environ.get("PIPEWIRE_REMOTE"))


def detect_audio_environment() -> dict:
    """
    Вернуть {available, warnings[], notices[]}.
    warnings — жёсткие причины блокировки голоса; notices — информационные.
    """
    warnings, notices = [], []
    fwd = has_forwarded_audio()

    if is_ssh():
        if fwd:
            notices.append("SSH + звуковой сервер проброшен — ок")
        else:
            warnings.append(
                "SSH: аудиоустройств нет. Пробросьте PULSE_SERVER или "
                "PIPEWIRE_REMOTE к звуковому серверу хоста."
            )

    if is_container():
        if fwd:
            notices.append("Контейнер + проброшен звук — ок")
        else:
            warnings.append(
                "Контейнер: нет аудио. Пробросьте PulseAudio/PipeWire socket."
            )

    if is_wsl():
        if fwd:
            notices.append("WSL + звуковой сервер — ок")
        else:
            notices.append(
                "WSL без PulseAudio: TTS-воспроизведение через PowerShell-фоллбэк; "
                "запись (микрофон) требует PULSE_SERVER=unix:/mnt/wslg/PulseServer."
            )

    return {"available": not warnings, "warnings": warnings, "notices": notices}


if __name__ == "__main__":
    import json
    print(json.dumps(detect_audio_environment(), ensure_ascii=False, indent=2))
