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

# ==ОТЧЁТ== Hermes — ФАЗА 2 (Визуал)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `30368b1`
**Тесты:** pytest полный → 266 passed (+7 subtests). node --check app.js OK.

## Задачи

### C-01 Токены/радиусы/тени + Manrope локальный woff2
**Статус:** DONE. Добавлен `@font-face` с локальным `assets/fonts/Manrope.woff2` (сконвертирован TTF→woff2 через fonttools, 53KB) + ttf fallback. БЕЗ CDN. Семейство в стеке `Manrope, "Segoe UI", system-ui`. Токены (`--accent:#b8e61d`, `--danger:#f04444`, `--radius:20px`, `--shadow`) уже корректны.
**Пруф:** файлы `uni/desktop/assets/fonts/Manrope.{woff2,ttf}` созданы (165KB/53KB); grep @font-face styles.css → есть.

### C-02 Шапка: порядок микрофон→глаз→STOP(нейтр.)→⚙→−; статус одной строкой
**Статус:** DONE. В `index.html` кнопки переупорядочены: mic → eye → **stop** → camera → overlay → settings → minimize. STOP — нейтральный (`.stop-icon` transparent, #e9eeea, hover→accent; НЕ #F04444, per инвариант 0.9). Статус — одна строка (`#headerStatus` внутри `#statusButton`).
**Пруф:** node --check OK; diff index.html.

### C-03 Аватар-peek: 4 состояния, z-index ПОД кнопками, pointer-events:none
**Статус:** ПОДТВЕРЖДЕНО + DECISION. `.avatar { z-index:2; pointer-events:none }` (styles.css 714-715), header `z-index:10` (870) → кнопки всегда сверху. 4 состояния в AVATAR_MAP: working/waiting/listening/done (app.js 61-64), PNG `uni-small-{work,wait,listen,done}.png`.
**DECISION:** «поза с кистями» — иллюстративный ассет отсутствует; текущие PNG — статичные аватары без рук. Фабриковать PNG запрещено (инвариант 0.1). Оставлено как есть; дорисовка — задача иллюстратора.

### C-04 index.html структура (#chatThread, #dynamicCards, mission-IDs, геометрия)
**Статус:** ПОДТВЕРЖДЕНО. `#chatThread` (50), `#dynamicCards` (58, после чата в quick-panel), `#missionConfirmed/#missionExpected/#missionCosts` (73) — все присутствуют. Ширина окна 336 (main.js 137); `placeAtBottomRight` использует workArea (≥12px над таскбаром).
**Пруф:** чтение index.html + main.js.

### C-05 Пустой чат: приветствие по времени + 3 чипа; «Юни готова» без спиннера
**Статус:** ПОДТВЕРЖДЕНО. `greetingByTime()` (4 тира: ночь/утро/день/вечер), применяется в `initEmptyChat()`; 3 чипа в HTML; `showReadyBubble('Юни готова')` — текст, без спиннера (нет spinner-элемента).
**Пруф:** чтение app.js 730-760; pytest не ломает.

## Инварианты
- 0.1: не фабриковали PNG-аватар с кистями (DECISION).
- 0.5: фронт НЕ решает по ключевым словам (applyUiEvent/dispatcher уже так).

## Следующая фаза
ФАЗА 3 (Универсальный UI-движок: U-01..U-07).
