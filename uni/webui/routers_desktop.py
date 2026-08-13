"""Десктоп-хелперы WebUI (Директива §6 Q-08 — модуляризация server.py).

Выделено из uni/webui/server.py как первый шаг разбиения монолитного
HTTP-обработчика на роутеры. Функции чистые (только модульные глобы _ROOT
импортируются из .server), не меняют поведение.
"""
from __future__ import annotations

from pathlib import Path

# 🤖 _ROOT — единый корень проекта, определён в server.py
from .server import _ROOT


def selftest_last() -> dict:
    """Последний сохранённый отчёт самотеста (runtime/logs/selftest_<дата>.md)."""
    logs_dir = _ROOT / "runtime" / "logs"
    try:
        import glob
        files = sorted(glob.glob(str(logs_dir / "selftest_*.md")), reverse=True)
        if not files:
            return {"ok": False, "error": "отчёт самотеста ещё не создан (POST /api/selftest {\"save\":true})"}
        txt = Path(files[0]).read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "report_path": files[0], "markdown": txt}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mouse_demo() -> dict:
    """Демо «Мышь Юни»: 3 клика в safe-зоне + рисунок (кольцо/бейдж «Юни»)."""
    try:
        import asyncio
        import tkinter  # бейдж требует дисплея
        from uni.capabilities.human_mouse import HumanMouseController, HumanMouseSettings
    except Exception as e:
        return {"ok": False, "error": f"HumanMouseController/бейдж недоступен: {type(e).__name__}: {e}",
                "hint": "нужен Windows + дисплей + win32 + tkinter"}
    try:
        import math
        import win32api
        ctrl = HumanMouseController(HumanMouseSettings(show_badge=True, move_duration=0.5))
        w, h = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        m = 140  # safe-зона: отступ >=140px от краёв
        pts = [
            (max(m, w // 2 - 200), max(m, h // 2 - 120)),
            (min(w - m, w // 2 + 200), max(m, h // 2 - 120)),
            (min(w - m, w // 2 + 200), min(h - m, h // 2 + 120)),
        ]
        async def _run() -> None:
            for (x, y) in pts:
                await ctrl.click(x, y)            # лайм-кольцо + «Юни»
                await asyncio.sleep(0.4)
            # рисунок: круг (демонстрация траектории)
            cx, cy, r = w // 2, h // 2 + 220, 90
            arc = [(int(cx + r * math.cos(a)), int(cy + r * math.sin(a)))
                   for a in [i * math.pi / 18 for i in range(37)]]
            await ctrl.move_to(*arc[0])
            for (x, y) in arc[1:]:
                await ctrl.move_to(x, y)
                await asyncio.sleep(0.01)
        asyncio.run(_run())
        ctrl.close()
        return {"ok": True, "points": pts, "drawn": "circle",
                "note": "клики + кольцо «Юни» выполнены в safe-зоне"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "hint": "win32api доступен? дисплей есть? STOP прервал?"}


def overlay_capture() -> dict:
    """Скриншот оверлея: через Desktop Companion (electron) capturePage (best-effort)."""
    cand = _ROOT / "runtime" / "logs" / "overlay_capture.png"
    if cand.is_file():
        import base64
        b64 = base64.b64encode(cand.read_bytes()).decode("ascii")
        return {"ok": True, "image_b64": "data:image/png;base64," + b64,
                "source": "overlay_capture.png"}
    return {"ok": False, "error": "скриншот оверлея ещё не сделан",
            "hint": "кнопка «Скриншот» в оверлее / electron capturePage"}
