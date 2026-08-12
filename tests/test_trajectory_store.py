"""Тест сохранения траекторий (B-05)."""

from __future__ import annotations

from unittest import mock

from uni.tools import trajectory_store as ts


def test_save_and_load_trajectory(tmp_path, monkeypatch):
    # перенаправляем путь траекторий во временную папку
    p = tmp_path / "trajectories.jsonl"
    monkeypatch.setattr(ts, "_TRAJ_PATH", p)
    monkeypatch.setattr(ts, "_TRAJ_DIR", tmp_path)

    rec = ts.save_trajectory("открой блокнот", [{"action": "click", "x": 1, "y": 2}],
                             ["сделала", "проверила"])
    assert rec["goal"] == "открой блокнот"
    assert rec["status"] == "success"
    loaded = ts.load_trajectories()
    assert len(loaded) == 1
    assert loaded[0]["goal"] == "открой блокнот"
    assert loaded[0]["history"] == ["сделала", "проверила"]


def test_suggest_skill_from_trajectory():
    rec = {
        "goal": "открой блокнот",
        "history": ["шаг 1: вижу", "шаг 1: сделала — клик", "шаг 1: проверила — достигнута"],
    }
    skill = ts.suggest_skill_from_trajectory(rec)
    assert skill is not None
    assert skill["trigger"] == "открой блокнот"
    assert skill["source"] == "trajectory"
    assert len(skill["steps"]) == 3
    assert skill["name"].startswith("uni-action-")


def test_suggest_skill_insufficient_data():
    # слишком короткая история -> None
    assert ts.suggest_skill_from_trajectory({"goal": "x", "history": ["только один шаг"]}) is None
    # пустая цель -> None
    assert ts.suggest_skill_from_trajectory({"goal": "", "history": ["а", "б"]}) is None


def test_save_trajectory_called_on_success(monkeypatch):
    # проверяем, что act_on_screen вызывает save_trajectory при успехе
    from uni.tools.visual_action import VisualActionAgent
    from uni.contracts import ToolResult

    class _Comp:
        use_human_motion = True
        clicks = []
        async def click_human(self, x, y, button="left"):
            self.clicks.append((x, y))
            return ToolResult(success=True, message="ok")

    class _Vis:
        def __init__(self): self.locate = 0; self.analyze = 0
        async def find_desktop_element(self, d):
            return ToolResult(success=True, data={"x": 10, "y": 10, "width": 5, "height": 5, "confidence": 0.9})
        async def analyze_desktop(self, p):
            self.analyze += 1
            return ToolResult(success=True, data={"analysis": "да, достигнуто"}, message="да")

    saved = {}
    def fake_save(goal, steps, history, status="success", meta=None):
        saved["goal"] = goal; saved["status"] = status
        return {}
    monkeypatch.setattr(ts, "save_trajectory", fake_save)

    agent = VisualActionAgent(_Comp(), _Vis())
    import asyncio
    out = asyncio.run(agent.act_on_screen("открой блокнот"))
    assert out["status"] == "success"
    assert saved.get("goal") == "открой блокнот"
    assert saved.get("status") == "success"
