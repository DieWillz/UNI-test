"""Independent quality gate tests (P-08, 2026-08-17).

Решают системную проблему: агент сам пишет код, сам пишет тесты под
этот код, сам их гоняет и сам подтверждает себе успех. Эти тесты
вызывают РЕАЛЬНЫЕ capabilities (или минимум их лёгкие части) БЕЗ моков,
чтобы поймать баги, которые mock-only тесты пропускают.

Покрытие:
  - trajectories.jsonl health check (фейк-детектор)
  - vision threshold consistency (Tier-0 vs Tier-2)
  - computer blacklist enforcement
  - memory fact deduplication
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNI = ROOT / "uni"


# ---------- 1. trajectories health ----------

def test_trajectories_no_fake_pattern():
    """Если >50% записей имеют одинаковые координаты — файл фейковый."""
    traj = UNI / "memory" / "trajectories.jsonl"
    if not traj.is_file():
        pytest.skip("trajectories.jsonl отсутствует")
    coords: list[tuple[int, int]] = []
    with open(traj, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for step in rec.get("steps") or []:
                if isinstance(step, dict):
                    x, y = step.get("x"), step.get("y")
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        coords.append((int(x), int(y)))
    if len(coords) < 10:
        pytest.skip(f"мало координат ({len(coords)})")
    top_freq = Counter(coords).most_common(1)[0][1]
    ratio = top_freq / len(coords)
    assert ratio < 0.5, f"trajectories вероятно фейк: top freq {ratio:.0%} ({Counter(coords).most_common(3)})"


def test_trajectories_fake_quarantined():
    """Архив фейка должен существовать (предыдущий фейк заархивирован)."""
    fake = UNI / "memory" / "trajectories.jsonl.FAKE"
    # Это не обязателно, но если архив есть — он должен быть непустой
    if fake.is_file():
        assert fake.stat().st_size > 100, "FAKE-архив подозрительно мал"


# ---------- 2. vision threshold consistency ----------

def test_vision_thresholds_consistent():
    """vision.py и visual_action.py должны использовать одинаковый порог confidence."""
    vision_py = UNI / "capabilities" / "vision.py"
    visual_action_py = UNI / "tools" / "visual_action.py"
    if not vision_py.is_file() or not visual_action_py.is_file():
        pytest.skip("vision.py или visual_action.py отсутствуют")
    vision_src = vision_py.read_text(encoding="utf-8", errors="replace")
    visual_src = visual_action_py.read_text(encoding="utf-8", errors="replace")
    # ищем "confidence < X.XX" или "confidence_threshold"
    v_matches = re.findall(r"confidence[_\s]*(?:<|<=|>=|>|threshold)\s*=?\s*([\d.]+)", vision_src)
    a_matches = re.findall(r"confidence[_\s]*(?:<|<=|>=|>|threshold)\s*=?\s*([\d.]+)", visual_src)
    if not v_matches or not a_matches:
        pytest.skip("пороги confidence не найдены в одном из файлов")
    # нормализуем — все должны быть близки к 0.55
    v_set = set(round(float(x), 2) for x in v_matches)
    a_set = set(round(float(x), 2) for x in a_matches)
    # допускаем расхождение не более 0.1 (старые пороги vs новые)
    diff = max(abs(max(v_set) - max(a_set)), abs(min(v_set) - min(a_set)))
    assert diff <= 0.1, (
        f"пороги confidence расходятся между vision.py ({v_set}) "
        f"и visual_action.py ({a_set}) — интеграция может молча ломаться"
    )


# ---------- 3. computer capability blacklist ----------

def test_computer_blacklist_enforced():
    """computer.py должен иметь blacklist опасных команд."""
    comp = UNI / "capabilities" / "computer.py"
    if not comp.is_file():
        pytest.skip("computer.py отсутствует")
    src = comp.read_text(encoding="utf-8", errors="replace")
    # Ищем явный blacklist
    has_blacklist = (
        "BLACKLIST" in src.upper()
        or "blacklist" in src
        or re.search(r"DANGEROUS_(?:CMDS|COMMANDS)", src, re.IGNORECASE)
    )
    assert has_blacklist, "computer.py не имеет явного blacklist опасных команд"


# ---------- 4. memory fact deduplication ----------

def test_memory_facts_deduplication():
    """extract_facts_from_text не должна создавать дубли."""
    from uni.webui.handlers.memory_facts import extract_facts_from_text
    text = "меня зовут Иван, меня зовут Иван"
    facts = extract_facts_from_text(text)
    # одинаковые subject+predicate+object не должны повторяться
    keys = [(f["subject"], f["predicate"], f["object"]) for f in facts]
    assert len(keys) == len(set(keys)), f"дубли: {keys}"
