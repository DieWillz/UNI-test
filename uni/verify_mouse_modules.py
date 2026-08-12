"""
Проверка перед объединением: сколько РЕАЛЬНО существует независимых реализаций
"человекоподобная мышь + подпись поверх курсора" в каноническом uni/.

Заявлено в разных источниках:
  A. uni/agent_cursor.py                              (Grok, из более раннего разбора)
  B. uni/motion/driver.py + trajectory.py + agent_cursor (Hermes, в этом файле)
  C. uni/capabilities/human_motion.py + human_mouse.py + uni_action_badge.py (Claude, этот чат)

Запуск из корня репозитория:
    C:\\LLM\\python312\\python.exe verify_mouse_modules.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNI = ROOT / "uni"

CANDIDATES = [
    ("A: agent_cursor.py",           UNI / "agent_cursor.py"),
    ("B: motion/driver.py",          UNI / "motion" / "driver.py"),
    ("B: motion/trajectory.py",      UNI / "motion" / "trajectory.py"),
    ("C: capabilities/human_motion.py", UNI / "capabilities" / "human_motion.py"),
    ("C: capabilities/human_mouse.py",  UNI / "capabilities" / "human_mouse.py"),
    ("C: capabilities/uni_action_badge.py", UNI / "capabilities" / "uni_action_badge.py"),
    ("C: capabilities/uni_cursor.py (browser overlay)", UNI / "capabilities" / "uni_cursor.py"),
]

print("=" * 70)
print("Что реально существует в uni/ прямо сейчас:")
print("=" * 70)
found = []
for label, path in CANDIDATES:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    mark = "[ЕСТЬ]" if exists else "[нет] "
    print(f"  {mark} {label:<45} {size if exists else '':>8}")
    if exists:
        found.append(label)

print()
print("=" * 70)
print("ИТОГ")
print("=" * 70)
groups_present = set()
if any(l.startswith("A") for l in found):
    groups_present.add("A (agent_cursor.py)")
if any(l.startswith("B") for l in found):
    groups_present.add("B (motion/driver.py + trajectory.py)")
if any(l.startswith("C") for l in found):
    groups_present.add("C (capabilities/human_motion.py + human_mouse.py)")

if len(groups_present) > 1:
    print(f"НАЙДЕНО {len(groups_present)} параллельных реализации: {', '.join(sorted(groups_present))}")
    print("-> Прежде чем писать что-либо новое — свести к ОДНОЙ. Не добавлять четвёртую.")
elif len(groups_present) == 1:
    print(f"Реально существует только: {list(groups_present)[0]}")
    print("-> Остальные — либо заявлены, но не написаны, либо в другой ветке/копии репозитория.")
else:
    print("Ни одна из трёх реализаций не найдена в каноническом uni/.")
    print("-> Можно спокойно ставить мои файлы (human_motion.py/human_mouse.py) как единственные.")
