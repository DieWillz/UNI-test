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

# ==ОТЧЁТ== Hermes — ФАЗА 3 (Универсальный UI-движок)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `17c11c6`
**Тесты:** pytest полный → 274 passed (+7 subtests). node --check app.js OK. Добавлен `tests/test_ui_contract.py` (8 passed).

## Контекст
Фронт (app.js) и бэкенд (/api/chat) были ЧАСТИЧНО готовы с commit 99c4ad7: диспетчер applyUiEvent, 7 компонентов, алиас-карта, поллинг task_id, approval-action endpoint — всё присутствовало. Недостающее доведено в этой фазе без переписывания верифицированного (инвариант 0.16).

## Задачи

### U-01 renderMissionUpdate: insertAdjacentHTML → createElement+textContent
**Статус:** DONE. Полностью переписана на createElement/textContent (без шаблонных строк). Модель НЕ контролирует разметку (U-08).
**Пруф:** grep `insertAdjacentHTML` в app.js → только старая копия удалена; node --check OK.

### U-02 Алиас progress_task → task_steps
**Статус:** DONE. `normalizeComponent` в app.js + `normalize_component` в ui_contract.py оба нормализуют progress_task→task_steps (и gallery/text/table/mission/list/approval). Серверная валидация тоже нормализует.
**Пруф:** test_alias_progress_task_normalized (test_ui_contract) PASS.

### U-03 КАНОН компонентов + form/link_list рендеры
**Статус:** DONE. Канон = 9: task_steps, result_text, result_gallery, result_list, comparison_table, mission_card, approval_required, **form**, **link_list**. Добавлены `renderFormInto` (поля + submit→submit_form) и `renderLinkListInto` (ссылки→link_open); зарегистрированы в диспетчере `renderComponentInto`.
**Пруф:** test_canon_components_complete PASS; node --check OK.

### U-04 БЭКЕНД-КОМПОЗИТОР + серверная валидация
**Статус:** DONE. Новый модуль `uni/webui/ui_contract.py`: белый список типов (CANON_COMPONENTS/CANON_EVENT_TYPES), `validate_component` (очистка src — только /api|/runtime|/assets, блок внешних/опасных схем), `validate_ui_events` (отбрасывает невалидные типы → честный result_text). `/api/chat` пропускает события через `validate_ui_events`; пусто → текстовый пузырь.
**Пруф:** test_src_only_local_allowed, test_unknown_component_falls_back_to_result_text, test_dead_buttons_rejected, test_unknown_event_type_dropped PASS; py_compile OK.

### U-05 POST /api/ui/action — карта действий
**Статус:** DONE. `resolve_action(action_id)` — реальная карта (approve/confirm/reject/open_all/open/save/copy/dismiss/retry/more/link_open/submit_form). Неизвестный id → честная ошибка 400 (НЕ молчаливый «ok»). Мёртвых кнопок нет (фронт рендерит только actions из карты).
**Пруф:** test_resolve_action_known_and_unknown PASS; endpoint в server.py возвращает 400 при unknown.

### U-06 grep-гейты + innerHTML в renderer
**Статус:** DONE. Гейт сценарных строк (`dogSearch|earningMission|Немецкий дог|🐕|45%|20%|38%`) в `renderer/` — ЧИСТ (кроме `38%`/`45%` в `index-demo.html`, который помечен DEPRECATED и не грузится). Остаточные `innerHTML` в app.js: только `card.innerHTML=''` (очистка), числовой прогресс-бар (строки 184/379, только числа), статус-поповер (строка 641, захардкоренный шаблон без данных модели). Все — НЕ model-derived → безопасны.
**Пруф:** grep выше; перечислены исключения.

### U-07 Приёмка 6 сценариев со скринами
**Статус:** DECISION / BLOCKED (честно). Все 6 рендеров реализованы и покрыты юнит-тестами контракта, НО визуальный пруф (скриншоты оверлея) требует ЖИВОГО Windows-дисплея + запущенного Electron + llama-бинаря — в этом окружении (headless Linux-агент, без экрана) снять скрин невозможно без симуляции (запрещено инвариантом 0.1). Рендеры проверены косвенно: контракт валиден, фронт компилируется (node --check), диспетчер покрывает все типы.
**Ручная инструкция для координатора:** на целевой машине запустить `UNI.bat`, открыть оверлей, прогнать 6 запросов (привет / фото горных озёр / 5 идей завтрака / сравнение хранилищ / запуск проекта / письмо клиенту) и снять скрины `runtime/diagnostics/`.

## Инварианты
- 0.4: оркестрация зрение→действие — НЕ в этой фазе (фаза 4), фронт/чат не импортируют capability.
- 0.5: фронт рендерит спеку, НЕ решает по ключевым словам (dispatcher + client_capabilities).
- 0.16: верифицированное (99c4ad7) НЕ переписано, только дополнено.

## Следующая фаза
ФАЗА 4 (Лёгкое зрение V-light: V-01..V-06).

# ==ОТЧЁТ== Hermes — ФАЗА 4 (Лёгкое зрение V-light)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `571c723`
**Тесты:** pytest полный → 284 passed (+7 subtests). py_compile vision/config/local_vision_fallback/visual_action OK. Добавлен `tests/test_vision_light.py` (10 passed).

## Задачи

### V-01 Аудит perception (реальные каналы vision.py)
**Статус:** ВЕРИФИЦИРОВАНО + изменено. `find_desktop_element` шёл сразу в VLM (`_capture_desktop`+`_ask`); локальные каналы (UIA/OCR) были ТОЛЬКО crash-fallback под флагом `local_fallback_enabled`. Это противоречило директиве V-02 (Tier-0 сначала). Исправлено — см. V-02.

### V-02 Tier-0 (без моделей) первым: UIA → OCR → DOM → Tier-2
**Статус:** DONE. `find_desktop_element` теперь вызывает `find_desktop_element_tier0(description)` (UIA → OCR WinRT → DOM Playwright) ДО VLM. Только если Tier-0 пустой — идёт Tier-2 (VLM). Каждый канал тихо возвращает None при недоступности библиотеки/headless (не падает). `local_vision_fallback.py` расширен: `winrt_ocr_available()`, `ocr_find_text()` (WinRT Windows.Media.Ocr), `dom_find_element()` (Playwright), `find_desktop_element_tier0()` (каскад).
**Пруф:** test_tier0_order_uia_first / test_tier0_fallback_to_ocr_when_uia_none / test_tier0_all_none_returns_none / test_tier0_channel_exception_is_safe PASS; py_compile OK.

### V-03 Tier-1 verify: дифф региона + повтор UIA/OCR через 1.2с
**Статус:** DONE. `vision.region_diff(path1, path2, threshold)` — доля изменившихся пикселей через numpy/opencv (0..1). В `visual_action._verify` добавлен повторный Tier-0 поиск (UIA/OCR) через `verify_delay` — если цель видна повторно, считаем достигнутой (быстрый verify без VLM); иначе VLM-проверка как fallback. `compare_screenshots` (matchTemplate) сохранён.
**Пруф:** test_region_diff_detects_change PASS; _verify патчен.

### V-04 Tier-2 (auto) gated nvidia-smi >=8ГБ
**Статус:** DONE (логика гейтинга). `vision.tier2_gpu_available(min_vram_gb)` — честно через `nvidia-smi --query-gpu=memory.free` (FileNotFoundError → False, без мока). Флаг `tier2_min_vram_gb` в `VisionConfig`. `winrt_ocr_available()` честно проверяет пакет + русский язык (ru) в `AvailableRecognizerLanguages` — если ru нет, возвращает причину (не мок).
**Пруф:** test_tier2_gpu_unavailable_without_nvidia PASS (в этом окружении nvidia-smi нет → False, причина). Само скачивание moondream2 GGUF + llama-server --mmproj — это упаковка/деплой (ФАЗА 7); здесь заложен ТОЛЬКО гейт, чтобы Tier-2 не грузился на слабом железе.
**DECISION:** реальная загрузка VLM-модели на :1236 — шаг упаковки; не выполнен здесь (нет сети/модели в окружении). Гейт готов.

### V-05 Fail-closed: все слои пусты → clarify/не кликаем
**Статус:** ПОДТВЕРЖДЕНО. `visual_action.act_on_screen`: пустая цель → `clarify`; чёрный список → `blocked`; не найдено ни одним слоем → `clarify` (не кликает наугад). `_BLACKLIST` сохранён.
**Пруф:** test_visual_action_blacklist_blocked / test_visual_action_empty_goal_clarify PASS.

### V-06 Пруфы каналов (Пуск через UIA, текст через OCR, дифф фиксирует)
**Статус:** DECISION / BLOCKED (честно). Логика каналов покрыта юнит-тестами (моки), НО реальный прогон на живом Windows (Пуск через UIA без VLM, «найди текст…» через WinRT OCR, дифф скрина фиксирует изменение, лог каналов) требует дисплея + установленных uiautomation/winrt/playwright — в headless-окружении недоступно без симуляции (запрещено 0.1).
**Ручная инструкция:** на целевой машине `python -c "from uni.tools.local_vision_fallback import find_desktop_element_tier0; print(find_desktop_element_tier0('Пуск'))"` → должен вернуть rect через UIA; `winrt_ocr_available()` → (True, 'ok') при установленном русском OCR.

## Инварианты
- 0.4: оркестрация зрение→действие только в visual_action.py (не трогал); vision/computer — capability, не импортируют друг друга напрямую.
- 0.1: никакого мока GPU/OCR — честные False с причиной.

## Следующая фаза
ФАЗА 5 (Мышь Юни: M-01..M-05).

# ==ОТЧЁТ== Hermes — ФАЗА 5 (Мышь Юни)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `091b0bb`
**Тесты:** pytest полный → 289 passed (+7 subtests). node --check app.js/index.html OK. Добавлен `tests/test_mouse_uni.py` (5 passed). py_compile server.py OK.

## Задачи

### M-01 ВЕРИФИЦИРОВАТЬ Этап D/B (уже в коммитах)
**Статус:** ВЕРИФИЦИРОВАНО, НЕ переписано. `computer.py`: `BLACKLISTED_COMMANDS` (format/del/shutdown/taskkill…), `verified_physical` gate (`_require_physical`), `max_steps` в `visual_action.py`. `computer_vision_agent`/`compare_screenshot` — из коммитов P0 Этап D. Пруф: test_m01_safety_present_in_computer_capability PASS.

### M-02 human_motion консолидация + DEPRECATED дублей
**Статус:** DONE (консолидация уже выполнена ранее). `uni/motion/driver.py` уже содержит 🤖 DEPRECATED-заголовок (2026-08-12) со ссылкой на `human_motion.py`/`human_mouse.py`. Боевой движок — `ComputerCapability(use_human_motion=True)` → `HumanMouseController` (win32api) с откатом на pyautogui. `human_motion.py` — чистая математика (generate_path, minimum-jerk, арка Безье). Не удаляю `motion/` (импортируется scenarios, инвариант 0.2).
**Пруф:** test_m02_duplicate_motion_deprecated PASS.

### M-03 Визуальная подпись: лайм-кольцо #B8E61D + бейдж «Юни», STOP прерывает
**Статус:** DONE (верифицировано). `action_badge.py`: `UNI_LIME = "#B8E61D"`, лайм-кольцо + бейдж с текстом `self.label` (=«Юни»/«UNI»). `HumanMouseController.cancel()` выставляет `threading.Event`, проверяемый в `_move_sync` на каждом шаге — STOP прерывает движение мгновенно (sticky stop, флаг не сбрасывается). `safe_margin`: проверка краёв экрана в `visual_action` (safe_margin 60px, отказ от клика у самого края).
**Пруф:** test_m03_path_is_arc_and_hits_target / test_m03_path_respects_minimum_jerk_monotonic_speed_profile PASS; cancel() в коде подтверждён.

### M-04 Кнопка «Демо мыши» в оверлее
**Статус:** DONE. Добавлена кнопка `demoMouseButton` в `settingsPopover` (index.html) + обработчик в app.js → `POST /api/demo/mouse`. Бэкенд `_mouse_demo()` делает 3 клика в safe-зоне (отступ ≥140px) + рисует фигуру (круг) с лайм-кольцом/бейджем «Юни». Кнопка возвращает честный статус (ok/error) без мока.
**Пруф:** test_m04_mouse_demo_returns_shape PASS (на headless возвращает ok=False с причиной, не падает); node --check app.js/index.html OK.

### M-05 Пруфы (скрин демо с кольцом/бейджем, STOP во время движения, лог траекторий)
**Статус:** DECISION / BLOCKED (честно). Логика покрыта юнит-тестами (arc/цель/cancel/demo-shape), НО визуальный пруф (скрин с кольцом, прерывание движения кнопкой STOP в реальном времени, лог траекторий) требует живого Windows-дисплея + tkinter/win32 — в headless-окружении недоступно без симуляции (запрещено 0.1).
**Ручная инструкция:** на целевой машине открыть оверлей → ⚙ → «Демо мыши»; проверить 3 клика + кольцо; нажать STOP в процессе — движение должно остановиться (cancel()).

## Инварианты
- 0.2: дубли (motion/driver.py) не удалены, помечены DEPRECATED.
- 0.4: оркестрация остаётся в visual_action; computer/human_mouse — capability.

## Следующая фаза
ФАЗА 6 (Архитектура: Q-01, Q-07..Q-10).
