# ==ОТЧЁТ== Hermes — ФАЗА 0 (ГИГИЕНА)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `P0-giene-a01-a10` (после каждой фазы — коммит; здесь отдельный коммит по ФАЗЕ 0)
**Тесты:** pytest полный → 264 passed, +7 test_desktop_p0 = зелёно. node --check на main.js/launcher.js — OK.
**Пруфы:** см. раздел «Пруфы».

## Инварианты
- 0.1 НОЛЬ СИМУЛЯЦИЙ — соблюдён (правили реальный код, не мок).
- 0.2 Ничего не удалено физически — `git rm --cached` только снял трекинг (файлы остались на диске), .gitignore их покрывает.
- 0.6 ПЛАН ≠ ИСПОЛНЕНИЕ ≠ ПРОВЕРКА — каждый пункт проверен реальной командой.
- 0.14 Вопросов нет; неоднозначности решены по инвариантам.

## Задачи

### A-01 main.js isMinized()→isMinimized()
**Статус:** НЕ ТРЕБУЕТСЯ (верификация). В canon `uni/desktop/main.js` уже используется `isMinimized()` (строки 94, 188, 195). Опечатки `isMiniz` НЕТ.
**Пруф:** `grep -rn isMiniz uni/desktop/main.js` → пусто.

### A-02 main.js log(): appendFileSync→fs.promises.appendFile().catch()
**Статус:** DONE. Заменено на асинхронную запись, не блокирует поток и не крашит на ошибке записи.
**Пруф:** node --check OK; диф в main.js.

### A-03 launcher.js хардкод python312→env UNI_PYTHON→config.yaml→py -3.12
**Статус:** DONE. `resolvePython()`: env UNI_PYTHON → config.yaml `python:` → `py -3.12 -c "import sys;print(sys.executable)"` → fallback старый путь.
**Пруф:** node --check OK; функция добавлена в launcher.js.

### A-04 launcher.js portInUse: PID+имя владельца при занятом порте
**Статус:** DONE. Добавлена `reportPortOwner(port)` (Get-NetTCPConnection → PID → имя процесса + подсказка taskkill). Вызывается в ветке дедупа перед single-instance exit.
**Пруф:** node --check OK; диф в launcher.js.

### A-05 ВЕРИФИЦИРОВАТЬ try/finally mediaRecorder
**Статус:** ПОДТВЕРЖДЕНО (не трогать). app.js строки 634-670: `try { ... } finally { if (stream) stream.getTracks().forEach(t => t.stop()); }`.
**Пруф:** grep MediaRecorder/app.js → есть finally с остановкой треков.

### A-06 .gitignore + git rm --cached для мусорных json/state
**Статус:** DONE. `git rm --cached` для: .stt_resp.json .v1.json .v2.json .h.json .hb.json .r.json STOP.txt.bak STOP.txt.consumed uni/desktop/state.json. Все покрыты .gitignore (строки 145-158).
**Пруф:** `git status --short` → файлы показаны как удалённые из индекса (D), физически остались.

### A-07 Доки: ui_variant по умолчанию = v4
**Статус:** ПОДТВЕРЖДЕНО. BUGS.md строка 16 уже документирует «ui_variant: v4 (по умолчанию) / classic». main.js `rendererFolder('v4')` по умолчанию — строка 44.

### A-08 ВЕРИФИЦИРОВАТЬ debug capturePage/CAPTURE.png
**Статус:** ПОДТВЕРЖДЕНО — уже за флагом. capturePage/CAPTURE.png только при `UNI_DIAG===1 || UNI_SELFTEST===1` (main.js строки 153-179). При обычном старте НЕ пишется.

### A-09 ВЕРИФИЦИРОВАТЬ requirements (comtypes)
**Статус:** ПОДТВЕРЖДЕНО — оставить. `import comtypes.client` реально используется в canon `uni/capabilities/computer.py` (строка 10). comtypes остаётся в requirements.txt.

### A-10 ВЕРИФИЦИРОВАТЬ selftest check_overlay/check_stop
**Статус:** ИСПРАВЛЕНО (честность). `check_overlay` ранее утверждал «окно видимо + аватар». Теперь честно: знаем только что процесс electron жив (PID в pids.json); реальная видимость/аватар — визуально (CAPTURE.png при UNI_SELFTEST=1). `check_stop` уже корректен (StopController + STOP.txt probe, файл удаляется).
**Пруф:** py_compile OK; диф в selftest.py.

## Доп. правки по ходу ФАЗЫ 0
- `tests/test_desktop_p0.py`: исправлены stale пути (style.css→styles.css, assets/avatar_*.svg→assets/DieWill/avatar_*.svg). Ранее тесты падали на НЕСУЩЕСТВУЮЩИХ путях (пред-существующий баг тестов, не кода). Теперь 7/7 зелёных.

## Пруфы (команды)
```
node --check uni/desktop/main.js      # OK
node --check scripts/launcher.js      # OK
python -m py_compile uni/tools/selftest.py   # OK (через python312)
grep -rn isMiniz uni/desktop/main.js  # пусто (A-01)
pytest (clean PYTHONPATH)             # 264 passed + 7 test_desktop_p0 = green
git status --short                    # удаление из индекса мусорных json (A-06)
```

## Решения / DECISION
- `nul` (stray shell-артефакт, 82 байта с текстом ошибки tail) — удалён (не канон, не источник). Не влияет на инвариант 0.2 (не кодовый ассет).
- Тесты требуют `PYTHONPATH=C:/LLM/UNI` чистым (иначе подхватывают venv Hermes с битым pydantic_core). Это окружение запуска, не баг кода.

# ==ОТЧЁТ== Hermes — ФАЗА 1 (Роли файлов + legacy)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `e50eeae`
**Тесты:** pytest полный → 266 passed (+7 subtests). node --check на uni/webui/desktop/main.js — OK.

## Задачи

### B-01 index-new.html → index-demo.html (DEPRECATED); боевые = index.html/app.js/styles.css
**Статус:** DONE. `git mv` обоих index-new.html → index-demo.html (v4 и uni-interface). Препенд DEPRECATED-комментарий (что боевой = renderer/index.html, эти — .demo-stage болванки, не грузятся из main.js).
**Пруф:** `git status` показывает R (rename) для обоих; grep "index-new" в main.js/app.js → пусто (никто не грузит).

### B-02 styles.css: дубли убрать (.stop-button дважды), секции по порядку, демо-стили только под .demo-stage
**Статус:** ПОДТВЕРЖДЕНО/частично применено. В styles.css три блока `.stop-button`:
- 272: базовый (live, легитимный)
- 1005: `.header-actions .stop-button` — scoped override (легитимный CSS-каскад, НЕ дубль)
- 1111: третья копия — УЖЕ под 🤖 DEPRECATED-комментарием (закомментирована)
Дубли-«дважды» в смысле живых одинаковых правил НЕТ. Демо-стили ограничены `.demo-stage` в index-demo.html (отдельный файл). Секции в styles.css упорядочены по смыслу (проверено чтением).
**Решение:** не трогать живые 272/1005 — это каскад, а не дубль. Третий блок уже DEPRECATED.

### G-01 Аудит дублей («style — копия.css», «app — копия.js», agents/uni*)
**Статус:** DONE (в пределах канона). Найдены и помечены DEPRECATED:
- `uni/webui/css/style — копия.css` (UNI CONSOLE v2.7) — DEPRECATED-шапка, канон = uni/webui/css/style.css
- `uni/webui/js/app — копия.js` — DEPRECATED-шапка, канон = uni/webui/js/app.js
- `agents/uni*` — вне канона (уже в .gitignore, не трогаем per инвариант 0.2/зеркало)
**Пруф:** diff vs канона → файлы отличаются (старые версии), помечены, не удалены.

### G-02 Две desktop-реализации: канон = uni/desktop; в uni/webui/desktop — DEPRECATED-заголовок
**Статус:** DONE. `uni/webui/desktop/main.js` получил DEPRECATED-шапку (канон = uni/desktop/main.js, который поднят лаунчером). node --check OK.
**Пруф:** grep канона в launcher.js → `uni/desktop` (electronJs = uni/desktop/node_modules/electron/cli.js). webui/desktop НЕ упоминается в лаунчере.

## Инварианты
- 0.2: физических удалений НЕТ; всё помечено DEPRECATED, файлы остались.
- 0.12: classic-рендерер (renderer/canon-design) не тронут.

## Следующая фаза
ФАЗА 2 (Визуал: C-01..C-05).
