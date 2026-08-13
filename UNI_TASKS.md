# UNI — актуальные задачи

Обновлено: 2026-08-13 (Hermes). Таблица отражает реально ведущиеся работы после фикс-шага.
Каждый факт со датой проверки. Статусы: `В РАБОТЕ`, `СДЕЛАНО`, `ЗАБЛОКИРОВАНО`, `ОЖИДАЕТ`.

## Таблица задач

| ID | Владелец | Статус | Цель | Критерий приёмки |
|---|---|---|---|---|
| T-FIX | Hermes | СДЕЛАНО (2026-08-13) | Исправить 6 падений pytest + создать `uni.check_architecture` | 264 passed / 0 failed; `check_architecture --strict` → 0/0 |
| T-FIX-STT | Hermes | СДЕЛАНО | Убрать загрузку Whisper на JSON-пробе `/api/stt` | реальный HTTP: JSON → 400 за 0.002 с, без загрузки модели |
| T-FIX-TESTS | Hermes | СДЕЛАНО | Исправить ошибочные тесты (hermes case) и patch-points (sd) | тесты проходят; детектят реальную регрессию, не ослаблены |
| T-FIX-PIPER | Hermes | СДЕЛАНО | Добавить Piper-голос и cwd-независимый поиск | ассет загружен (63 МБ); тест генерирует реальный аудио 22050 Гц |
| T-DESK | Hermes | СДЕЛАНО (код + live E2E) | Desktop Companion: 336×660, PNG avatar, STOP (нейтральная), tray «Выход»/«Стоп», пустой чат+чипы | `node --check` OK; живой Electron: 1 окно visible, позиция над треем (fixed), chat ответ; скрин outbox/HERMES_UI_IDLE.png |
| T-PACK | Hermes/координатор | ОЖИДАЕТ | One-click Windows-инсталлятор + встроенный runtime | см. `UNI_PROJECT_BRIEF.md`; бинарники llama.cpp уже в `downloads/` |
| T-LAUNCH | Hermes | СДЕЛАНО | Единый лаунчер: одно нажатие (ЮНИ.lnk→UNI.bat→launcher.js) поднимает llama:1235+webui:8787+electron; выход (tray «Выход») убивает ВЕСЬ стек по pids.json | `/api/launcher/stop` → порты free, pids.json удалён; дедуп (живой PID=reuse); коммит 6b682a8 |
| T-PUSH | Hermes | СДЕЛАНО | Запушить ВЕСЬ актуальный код в GitHub для анализа другими ИИ | ветка `clean/august-2026` запушена в `DieWillz/UNI-test` (НЕ main); рантайм-мусор в .gitignore |
| T-PRE-1 | Hermes | СДЕЛАНО | Воспроизвести и классифицировать актуальные падения | 6 падений → классы: 2 ошибочный тест, 2 patch-point, 1 prod-дефект, 1 внеш. зависимость |
| T-PRE-2 | Hermes | СДЕЛАНО | Проверить тесты на избыточный mock; добавить integration | сохранены unit-тесты; добавлены реальные HTTP-пруфы vision/admin/roles |
| T-PREP | Hermes | В РАБОТЕ | Подготовить артефакты для Codex (outbox) | `HERMES_PYTEST.xml` готов; `REPORT_HERMES_FINAL.md`, `CAPTURE.png`, `CODEX_SHOT_1.png` — в работе |
| T-POS | Hermes | СДЕЛАНО | Исправить позицию окна — ровно над треем (правый нижний, над панелью задач) | DIP-корректный `placeAtBottomRight` (workArea без sf, getSize); лог final y≈142 @DPI1.25; было y:0 (вверху) |
| T-AUDIT | Hermes | СДЕЛАНО | Создать `uni.check_architecture` (ADR-0005) | AST-скан capabilities; детектит violation (доказано инъекцией); `--strict` → 0/0 |
| T-VLM | Hermes | ОЖИДАЕТ | Встроить torch-free VLM для vision (упаковка) | вне scope фикс-шага; цель упаковки |

## Правила работы с задачами

1. Перед работой назначить себе задачу (ID из таблицы).
2. После — обновить только затронутые строки и дату проверки.
3. Не заявлять `СДЕЛАНО` без свежего наблюдаемого результата (ACTION→RESULT→OBSERVATION).
4. Mock/unit-тест ≠ E2E-доказательство.
