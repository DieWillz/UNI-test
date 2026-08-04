"""
UNI — проверка Шага 0 (см. UNI_IMPROVEMENT_PLAN_v3.md, раздел «Спорные пункты»).

Ничего не меняет в коде — только читает файлы и печатает, что нашло.
Запускать из корня репозитория (там, где лежит папка uni/):

    C:\\LLM\\python312\\python.exe verify_step0.py

Три проверки:
  1. contracts.py — единый ли канонический контракт (Hermes) или есть дубли
     в planner_interface.py (Copilot/DeepSeek)?
  2. planner.py / planner_interface.py — реально ли на них что-то ссылается
     в рантайме, или это мёртвый код (Hermes)?
  3. _API_ALIASES в tools/executors.py — правда ли dotted/underscore имена
     уже унифицированы (Hermes), или роутинг всё ещё ломается (Copilot)?

После скрипта — инструкция, как проверить сам вебUI (раунд 2 из плана).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNI = ROOT / "uni"

def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

def show_matches(path: Path, pattern: str, context: str, max_hits: int = 8):
    if not path.exists():
        print(f"  [нет файла] {path.relative_to(ROOT)}")
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines, start=1):
        if re.search(pattern, line):
            hits.append((i, line.strip()))
    print(f"  {path.relative_to(ROOT)}  ({context})")
    if not hits:
        print("    -> совпадений не найдено")
    else:
        for ln, txt in hits[:max_hits]:
            print(f"    {ln}: {txt[:110]}")
        if len(hits) > max_hits:
            print(f"    ... ещё {len(hits) - max_hits} совпадений")
    return hits


# ---------------------------------------------------------------------
section("ПРОВЕРКА 1: contracts.py — единый контракт или дубль в planner_interface.py?")
# ---------------------------------------------------------------------
contracts = UNI / "contracts.py"
if contracts.exists():
    text = contracts.read_text(encoding="utf-8", errors="replace")
    print(f"  uni/contracts.py: {len(text)} байт")
    for cls in ["ToolResult", "Action", "ActionResult", "AgentContext", "Observation"]:
        found = bool(re.search(rf"class\s+{cls}\b", text))
        print(f"    class {cls} определён здесь: {'да' if found else 'нет'}")
else:
    print("  [нет файла] uni/contracts.py")

results_py = UNI / "tools" / "results.py"
if results_py.exists():
    text = results_py.read_text(encoding="utf-8", errors="replace")
    is_reexport = "import" in text and "class ToolResult" not in text
    print(f"\n  uni/tools/results.py: {'похоже на re-export (Hermes прав)' if is_reexport else 'содержит собственное определение (возможен дубль)'}")
    print("  " + "\n  ".join(l for l in text.splitlines() if l.strip())[:400])

planner_interface = UNI / "planner_interface.py"
show_matches(planner_interface, r"class\s+(Action|ActionResult|AgentContext|Observation)\b",
             "ищем дублирующие определения контрактов")


# ---------------------------------------------------------------------
section("ПРОВЕРКА 2: planner.py / planner_interface.py — используются ли в рантайме?")
# ---------------------------------------------------------------------
py_files = list(UNI.rglob("*.py"))
callers = []
for f in py_files:
    if f.name in ("planner.py", "planner_interface.py"):
        continue
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if re.search(r"\bPlannerImpl\b", text) or re.search(r"from\s+uni\.planner(_interface)?\s+import", text) or re.search(r"import\s+uni\.planner", text):
        for i, line in enumerate(text.splitlines(), start=1):
            if "PlannerImpl" in line or "planner_interface" in line or re.search(r"\bimport\s+.*\bplanner\b", line):
                callers.append((f.relative_to(ROOT), i, line.strip()))

if not callers:
    print("  Ссылок на PlannerImpl / planner_interface вне самих файлов planner*.py НЕ найдено.")
    print("  -> подтверждает утверждение Hermes: planner, похоже, не подключён к рантайму.")
else:
    print(f"  Найдено {len(callers)} ссылок вне planner*.py:")
    print("  -> противоречит утверждению Hermes, planner ГДЕ-ТО используется:")
    for path, ln, txt in callers[:15]:
        print(f"    {path}:{ln}: {txt[:110]}")


# ---------------------------------------------------------------------
section("ПРОВЕРКА 3: _API_ALIASES в tools/executors.py — dotted/underscore уже унифицированы?")
# ---------------------------------------------------------------------
executors = UNI / "tools" / "executors.py"
hits = show_matches(executors, r"_API_ALIASES", "ищем механизм алиасов имён действий")
if hits:
    print("  -> подтверждает Hermes: алиасинг dotted/underscore уже есть.")
else:
    print("  -> НЕ найдено — либо файл называется иначе, либо Hermes ошибся/имел в виду другую версию.")
    print("  Попробуй вручную: grep -rn \"_API_ALIASES\\|dotted\\|underscore\" uni/tools/")


# ---------------------------------------------------------------------
section("ИТОГ")
# ---------------------------------------------------------------------
print("""
  Сохрани вывод этого скрипта — он и есть ответ на вопрос "кто был прав".
  Дальше, по плану (Шаг 0, пункт 2):

  1. Запусти вебUI:
       cd C:\\LLM\\UNI
       set PYTHONPATH=C:\\LLM\\UNI
       C:\\LLM\\python312\\python.exe -m uni.webui --port 8787

  2. В другом терминале проверь реальный ли бэкенд отвечает:
       C:\\LLM\\python312\\python.exe -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://127.0.0.1:8787/api/participants')))"

     Если видишь список участников с реальными полями (не ошибку соединения) —
     бэкенд поднят и Шаг 1 можно начинать. Если ConnectionRefusedError —
     значит /api/participants либо не реализован в server.py, либо сервер
     не стартовал (смотри вывод шага 1 в консоли).
""")
