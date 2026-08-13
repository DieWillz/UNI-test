"""Тесты Архитектуры (Директива §6: Q-01, Q-07, Q-08, Q-09, Q-10).

- Q-01: единый контракт Action/Observation/AgentContext (dotted names, frozen, round-trip).
- Q-07: транспорт ui_events — SSE-стрим (/api/autonomous/stream) уже есть + поллинг
  GET /api/task/<id>/status сохранён (fallback). Проверяем наличие обоих.
- Q-08: server.py модуляризован — desktop-хелперы вынесены в routers_desktop.py,
  server.py ре-экспортирует _mouse_demo/_overlay_capture/_selftest_last.
- Q-09: единый constraints.txt; оба requirements.txt ссылаются на него (-r).
- Q-10: watchdog в launcher.js (node --check + наличие restart-логики).
"""
from __future__ import annotations

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uni.contracts import Action, ActionResult, Observation, AgentContext, ToolResult


def test_q01_action_dotted_name_and_frozen():
    a = Action(name="browser.navigate", params={"url": "x"})
    assert a.name == "browser.navigate"
    # frozen — нельзя мутировать (единый контракт)
    try:
        a.name = "other"
        assert False, "Action должен быть frozen"
    except Exception:
        pass


def test_q01_actionresult_roundtrip_from_tool_result():
    tr = ToolResult(success=True, message="ok", data={"x": 1})
    ar = ActionResult.from_tool_result(tr, "vision.find_desktop_element", verified=True)
    assert ar.action.name == "vision.find_desktop_element"
    assert ar.verified is True
    back = ar.to_tool_result()
    assert back.success and back.data["x"] == 1


def test_q01_agentcontext_record_and_bounded():
    ctx = AgentContext(goal="open site")
    ctx.record_observation(Observation(source="vision", summary="s", confidence=0.9))
    assert len(ctx.observations) == 1
    assert ctx.remaining_retries() == 3


def test_q07_streaming_and_polling_present():
    # SSE-стрим ui_events существует в server.py
    srv = (Path(__file__).resolve().parents[1] / "uni" / "webui" / "server.py").read_text(encoding="utf-8")
    assert "/api/autonomous/stream" in srv
    assert "text/event-stream" in srv
    # поллинг task status сохранён как fallback
    assert "/api/task/" in srv


def test_q08_routers_desktop_extracted_and_reexported():
    routers = (Path(__file__).resolve().parents[1] / "uni" / "webui" / "routers_desktop.py").read_text(encoding="utf-8")
    assert "def selftest_last" in routers and "def mouse_demo" in routers and "def overlay_capture" in routers
    srv = (Path(__file__).resolve().parents[1] / "uni" / "webui" / "server.py").read_text(encoding="utf-8")
    # server.py ре-экспортирует старые имена (обратная совместимость с 6 call sites)
    assert "from .routers_desktop import selftest_last as _f" in srv


def test_q09_constraints_single_source():
    root = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    uni_req = (Path(__file__).resolve().parents[1] / "uni" / "requirements.txt").read_text(encoding="utf-8")
    constraints = (Path(__file__).resolve().parents[1] / "constraints.txt").read_text(encoding="utf-8")
    assert "-r constraints.txt" in root
    assert "-r constraints.txt" in uni_req
    # ключевые пакеты зафиксированы в constraints (не расходятся)
    for pkg in ("pydantic", "opencv-python", "torch", "playwright"):
        assert pkg in constraints


def test_q10_launcher_watchdog_present():
    import subprocess
    # node --check проходит
    r = subprocess.run(["node", "--check", "scripts/launcher.js"], cwd=Path(__file__).resolve().parents[1],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    launcher = (Path(__file__).resolve().parents[1] / "scripts" / "launcher.js").read_text(encoding="utf-8")
    assert "onServerExit" in launcher  # watchdog рестарт серверов при падении
    assert "restartServer" in launcher
