# BUGS.md — постоянный канал багов (Юни / Hermes)

Формат координатора: `- [ ] описание (дата)`
Hermes берёт по порядку, чинит, помечает `- [x] исправлено (коммит, пруф)`.

## Открытые
- [ ] (ставь сюда строки — Hermes берёт по порядку)

## Исправлено
- [x] (пример) самотест падал на отсутствии TTS — сделал честное «НЕ ПРОВЕРЕНО» (2026-08-13, Hermes)
- [x] `ComputerCapability.launch_app` NameError в `finally` (uni/capabilities/computer.py): внешний `finally` безусловно делал `return ToolResult(..., f"Ошибка: {e}")`, где `e` не определена в области видимости → любой launch_app падал NameError и гасил успешный return из try. **Исправлено Hermes (2026-08-14):** убран безусловный `return` из `finally`, теперь `finally` только `release_lock(lock_name)`, результат определяется return-ами из `try`/`except`. Старый код помечен `DEPRECATED by Hermes` в файле. Пруф: `PYTHONPATH= c:/LLM/python312/python.exe -m pytest tests/integration/test_contracts_and_features.py -q -p no:cacheprovider` → passed (launch_app тесты зелёные).

## Заметки (2026-08-14, Claude — восстановление мыши/зрения в интерфейсе)
- **Мышь**: `uni/capabilities/human_mouse.py` физически отсутствовал на диске (импортировался из computer.py и routers_desktop.py, поэтому click_human/double_click_human/drag_human и кнопка «Демо мыши» падали). Создан заново: кривая Безье + минимально-рывковый профиль скорости, лайм-кольцо через уже существующий uni/action_badge.py. `py_compile` пройден, живой запуск на машине координатора не делался.
- **Зрение**: кнопка 👁 в оверлее только писала consent в журнал, реальный захват не запускался: IPC `observeTick` в main.js существовал, но `app.js` его нигде не вызывал; `/api/vision/capture` возвращал только эхо image_b64 без анализа, хотя main.js ждал `d.caption`. Добавлен `POST /api/vision/observe` (uni/webui/server.py): агент сам снимает рабочий стол (vision.analyze_desktop, независимый ImageGrab — картинка от Electron не нужна), прогоняет caption через uni/desktop/observe.py::suggest (бюджет+тихие часы), кладёт инициативу в SSE-очередь. `app.js`: добавлен таймер раз/18с (только при state.observing) + подписка window.uni.onEvent на initiative/consent_changed (раньше нигде не вызывалась). `node --check` пройден.
- **Найдено, исправлено Hermes (2026-08-14)**: `launch_app` NameError-баг выше — перенесён в «Исправлено» с пруфом (см. выше).
- **Не проверено живьём запуском**: у Claude нет доступа к выполнению кода на машине координатора (только чтение/запись файлов через Filesystem MCP). Нужен живой прогон: кнопка «Демо мыши» в оверлее и включение 👁 при живом LLM (нужен config.yaml с vision.enabled=true и рабочим provider).

## Заметки по этому проходу (2026-08-13, директива «Единая точка входа + Самотест + Мышь Юни»)
- Лаунчер: `UNI.bat` → `scripts/launcher.js` (hidden-spawn llama+webui+electron, логи → runtime/logs/, pids.json, дедуп по PID и порту, single-instance, трей «Выход»).
- Бейдж мыши: `uni/action_badge.py` теперь лайм-кольцо #B8E61D + бейдж «Юни».
- Самотест: `uni/tools/selftest.py` + эндпоинты `/api/selftest`, `/api/demo/mouse`, `/api/desktop/capture`.
- ui_variant: v4 (по умолчанию) / classic (legacy), переключение в оверлее (canon-design).
- ЧЕСТНО: полный end-to-end (двойной клик UNI.bat → ≤60с оверлей «На связи») не прогнан в этом окружении — здесь нет Windows-дисплея/llama-бинаря/electron-рантайма в пути. Код собран и проверен синтаксически (node --check, py_compile); рантайм-пруфы (скриншоты, tasklist/netstat) нужно снять на целевой машине координатора.

## Заметки по проходу Hermes (2026-08-14 — MOUSE_VISION / MASTER)
- **Исправлено Hermes** (все 5 правок с `DEPRECATED by Hermes`-комментариями, не удаляют старый код):
  1. `launch_app` NameError в `finally` (computer.py) — см. «Исправлено».
  2. `config.load_config` гонка: добавлен кэш + ленивый `Lock` (без модульного `import threading`, чтобы не менять порядок загрузки пакета). Старый код помечен `DEPRECATED by Hermes`.
  3. `server.py /api/participants_dirs` рассинхрон с `/api/heartbeats`: оба теперь через `_gather_participants()` (источник истины — `load_participants()`, где `hermes` реальный участник).
  4. `speech._synthesize_audio_safe` был ошибочно ВЛОЖЕН в `_split_for_tts` (лишний отступ) → `self._synthesize_audio_safe` не существовал → `test_selected_voice_exports_wav` падал AttributeError. Вынесен на уровень класса.
  5. `server.py` SSE `/api/desktop/events`: цикл `while True` не выходил при disconnect клиента (висел 30с+, держа wfile/connection) → латентная гонка GC. Добавлен `break` при `wfile.closed`/BrokenPipe.
- **Честно НЕ проверено живьём** (нужен дисплей/LLM на машине координатора): кнопка «Демо мыши» в оверлее + лайм-кольцо; vision 👁 observe петля (18с, инициатива в чате); реальный launch_app с открывшимся окном notepad; архитектурный аудит 0/0 (пройден: `uni.check_architecture --strict` → 0 errors, 0 warnings); `node --check` app.js (пройден).
- **Остаточный риск**: полный `pytest` suite флейково крашится `Windows fatal exception: 0x80000003` (hard crash C-расширения при параллельном GC). Латентный дефект, присутствовал в baseline ДО моих правок (см. git-log P8/P9). Точечный прогон моих затронутых тестов → 17 passed, 0 failed. Лечение латентной гонки вынесено отдельно, не блокирует приёмку конкретных фиксов.
