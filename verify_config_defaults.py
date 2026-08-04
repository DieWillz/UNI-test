"""
Догоняющая проверка — единственный пункт из спорной таблицы v3, который
verify_step0.py не проверял: есть ли в config.py debug=True / allow_camera=True.

Запуск из корня репозитория:
    C:\\LLM\\python312\\python.exe verify_config_defaults.py
"""
import re
from pathlib import Path

path = Path(__file__).resolve().parent / "uni" / "config.py"
if not path.exists():
    print(f"[нет файла] {path}")
else:
    text = path.read_text(encoding="utf-8", errors="replace")
    for field in ["debug", "allow_camera", "allow_screenshot", "log_level"]:
        hits = [(i, l.strip()) for i, l in enumerate(text.splitlines(), 1) if re.search(rf"\b{field}\s*[:=]", l)]
        if hits:
            for ln, txt in hits:
                print(f"  {ln}: {txt[:100]}")
        else:
            print(f"  поле '{field}' в config.py НЕ найдено")
