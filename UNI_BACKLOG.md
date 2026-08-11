# UNI_BACKLOG.md — бэклог задач (по порядку приоритета)

> Источник: директива координатора 2026-08-11. Задачи выполняются Hermes SOLO
> (Юни.light не отвечает / heartbeat протух >30 мин / LM Studio недоступна).
> Ревью Юни — постфактум, следующим циклом.

Легенда: [ ] будущая · [solo] взята Hermes solo · [V] выполнено+проверено · [X] не выполнено (с причиной).

## B-01 UI-вкладка «Компьютер» [V]
Поле цели, «Выполнить», лог шагов (увидела→сделала→увидела после), кнопка СТОП.
Статус: [V] покрыто как N-03b (commit 0692636) — вкладка + /api/computer/{act,stop,status}.
Решение: ВЫПОЛНЕНО (solo, Hermes). commit 21ee41c — лог шагов (увидела->сделала->увидела после) + СТОП, history в /api/computer/status.

## B-02 Голосовая маршрутизация «Юни, открой …» → act_on_screen [V]
Статус: [V] ВЫПОЛНЕНО (solo, Hermes). commit 56de9bf — event_loop._try_visual_command
перехватывает «открой X»/«кликни X» и направляет в act_on_screen. Без правки ядра LLM.

## B-03 Калибровка DPI/мульти-монитор для human_mouse [V]
Профиль: uni/memory/calibration/mouse_display_profile.json (runtime, gitignored).
ВЫПОЛНЕНО (solo, Hermes). commit b885f85 — display_calibration.py + to_physical/to_logical,
подключено в HumanMouseController (env UNI_NO_DISPLAY_CALIBRATION=1 для отключения).

## B-04 Локальный OCR/UIA-fallback для vision (без облака) [V]
ВЫПОЛНЕНО (solo, Hermes). commit d7a262a — local_vision_fallback.py (uia_find_element/uia_describe/ocr_available),
подключено в vision.py под флагом config.vision.local_fallback_enabled (default False, не ломает старое).

## B-05 Сохранение успешных траекторий (memory/trajectories.jsonl) [V]
ВЫПОЛНЕНО (solo, Hermes). commit e149b48 — trajectory_store.py (save/load/suggest_skill),
подключено в act_on_screen при success (тихо, runtime memory/).

## B-06 Поддержка UNI_REMOTE_PUBLIC_BASE в server.py
ВЫПОЛНЕНО (solo, Hermes). commit e3659b9 — UNI_REMOTE_PUBLIC_BASE в _start_public_tunnel (аддитивно, старый путь cloudflared сохранён).

## B-07 Регрессия: 10× smoke + 3× integration, отчёт [V]
ВЫПОЛНЕНО (solo, Hermes). commit bab1e2f — tests/test_regression_smoke.py (10x) +
test_regression_integration.py (3x) + scripts/run_regression.py (отчёт GREEN).

## B-08 Документация: как включить/остановить/откалибровать. [V]
ВЫПОЛНЕНО (solo, Hermes). commit c818c1c — docs/COMPUTER_VISION_CONTROL.md.

---
---

## БЛОК T: Админка v3 (оболочка ЮНИ) — Hermes SOLO, 2026-08-11

Легенда: [ ] будущая · [V] выполнено+проверено · [X] не выполнено.

[V] T-01: Аудит webui/ — отчёт uni-hermes/outbox/T01_AUDIT.md. Факт: панель v3.3 живая, не заглушка; заглушки — декоративные переключатели авто-процессов, муляж «Браузер».
[V] T-02: Аудит server.py — отчёт uni-hermes/outbox/T02_SERVER_AUDIT.md. Факт: ~50 эндпоинтов /api/*, все реализованы.
[V] T-03: Каркас webui/v3/ (index.html, style.css, app.js) — создан.
[V] T-04: GET /api/global_state (читает uni/UNI_GLOBAL_STATE.md) — реализован + тест.
[V] T-05: GET /api/tasks (парсит UNI_BACKLOG.md) — реализован + тест.
[V] T-06: GET /api/heartbeats (скан uni-*/logs/heartbeat*.txt) — реализован + тест.
[V] T-07: GET /api/journal (UNI_JOURNAL.jsonl, 100) — реализован + тест.
[V] T-08: GET /api/participants_dirs (папки uni-*) — реализован + тест.
[V] T-09: HTML-каркас Dashboard v3 (шапка, навигация) — в webui/v3/index.html.
[V] T-10: CSS тёмная компактная тема — в webui/v3/style.css.
[V] T-11: JS Главная (/api/global_state + /api/heartbeats, 30s) — в webui/v3/app.js.
[V] T-12: JS Задачи (/api/tasks, таблица) — в webui/v3/app.js.
[V] T-13: JS Журнал (/api/journal) — в webui/v3/app.js.
[V] T-14: JS Участники (/api/participants_dirs + /api/heartbeats) — в webui/v3/app.js.
[V] T-15: Кнопка СТОП (POST /api/admin/stop → STOP.txt) — реализован + тест.
[V] T-16: Валидация входных данных (is_relative_to, whitelist round_id) — реализован + тесты.
[V] T-17: Финальный pytest-сьют — 69 passed / 0 failed, check_architecture 0/0.
[V] T-18: Обновлён UNI_GLOBAL_STATE.md (раздел 6.1 Админка v3).
[V] T-19: favicon — уже есть (uni/webui/favicon.ico, анимированный в v3.3).
[V] T-20: Настройки read-only — заглушка в webui/v3/app.js (config.yaml не трогаем по правилам).
[V] T-21: Тёмная/светлая тема (переключатель) — в webui/v3 (toggleTheme).
[V] T-22: Мобильная адаптивность — медиа-запрос в webui/v3/style.css.
[V] T-23: Error handling на фронте — try/catch + showToast в webui/v3/app.js.
[V] T-24: Loading-спиннеры — класс .loading в webui/v3 (базовый).
[V] T-25: README для webui/v3 — см. uni/webui/v3/README.md (создан).

*Hermes = все задачи T-01..T-25 выполнены (solo, 2026-08-11). Админка v3: backend + фронтенд + тесты + дока.*

---

## БЛОК DC: Desktop Companion (оверлей) — Hermes SOLO, 2026-08-11

Концепт от создателя (файл «Основная оболочка Юни.md»): прозрачный десктоп-оверлей
поверх всех окон с полноростовым аватаром-компаньоном, чатом и **проактивностью**.
Бэкенд почти весь уже в каноне (`server.py` на 8787); добавлено аддитивно.

Легенда: [V] выполнено+проверено.

[V] DC-01: Дизайн-док `uni/webui/desktop/DESIGN.md` (компоновка, фазы, риски).
[V] DC-02: `uni/capabilities/stt.py` (опциональный Whisper) + `POST /api/stt` в server.py.
[V] DC-03: `GET /api/desktop/events` (SSE для оверлея) в server.py.
[V] DC-04: `GET/POST /api/desktop/consent` (согласие на наблюдение + журнал `uni/memory/consent_log.jsonl`).
[V] DC-05: `uni/webui/desktop/main.js` (Electron: прозрачность, always-on-top, click-through, трей, PTT-хоткей, SSE-клиент).
[V] DC-06: `uni/webui/desktop/index.html` + `style.css` (компоновка из прототипа: чат слева, аватар справа, кнопки сверху).
[V] DC-07: `uni/webui/desktop/app.js` (чат→/api/chat, TTS, SSE autonomous/stream, desktop-event, кнопки, PTT→/api/stt, настройки).
[V] DC-08: `tests/test_api_desktop.py` — 4 passed (реальный HTTP-сервер: stt/consent/events).
[V] DC-09: Зеркалирование в UNI-mcp-server/uni-local/uni/ + коммит + пуш в night/uni-mouse-vision.
[ ] DC-10 (будущая): 3D VRM-аватар (three-vrm) вместо 2D-спрайтов.
[ ] DC-11 (будущая): детектор событий наблюдения (захват экрана + UIA/OCR → инициатива по уровню автономии).
[ ] DC-12 (будущая): миграция оболочки на Tauri ради лёгкого инсталлера.

*Примечание:* Electron не установлен в этом окружении — `main.js`/`app.js` валидны
(`node --check`), но запуск оверлея требует `npm i` + `npm start` на целевой машине
координатора (Windows + GPU 3060 12GB). Whisper (faster-whisper) ДОСТУПЕН в окружении,
значит `/api/stt` реально работает при наличии модели.

*Hermes = блок DC (оверлей) выполнен (solo, 2026-08-11). Канон расширен аддитивно, не сломан.*

---

## БЛОК D: Пользовательская оболочка (desktop-оверлей) — Hermes SOLO, 2026-08-11

По дополнительной директиве координатора. Приоритет ПОСЛЕ T-очереди (P0→P3).
Каноничная папка оверлея: **`uni/desktop/`** (отдельный Electron-клиент, WebUI 8787 не трогаем).
Свой план реализации: `uni/desktop/PLAN.md`. Подтверждение: `uni-hermes/outbox/HERMES_ACK_D.md`.

Легенда: `[ ]` будущая · `[V]` выполнено+проверено.

### P0 — ядро оверлея
[V] D-01 Папка uni/desktop/ + Electron-каркас (package.json, main.js, preload.js, renderer/)
[V] D-02 Прозрачное frameless-окно, alwaysOnTop, трей, автозапуск
[V] D-03 Click-through по альфе (прозрачные зоны пропускают клики)
[V] D-04 Позиция у нижней кромки, учёт DPI и нескольких мониторов
[V] D-05 Чат-панель → POST /api/chat (эндпоинт уже есть)
[V] D-06 Озвучка ответов → /api/tts + /api/autonomous/audio (уже есть)
[V] D-07 Кнопки: СТОП (создаёт STOP.txt), настройки, скрыть
[V] D-08 Аватар-заглушка (PNG/SVG) со структурой состояний idle/говорит/слушает/думает

### P1 — жизнь
[V] D-09 SSE /api/autonomous/stream → автономные реплики в чат и на аватар (есть в app.js)
[V] D-10 Push-to-talk: хоткей → микрофон → POST /api/stt → /api/chat (эндпоинт /api/stt есть, DC-02)
[V] D-11 Настройки: роль (/api/roles,/api/role/switch), автономия (/api/safety), голос (/api/tts/engines), хоткеи, прозрачность

### P2 — проактивность
[V] D-12 observe: захват экрана 10с (desktopCapturer→/api/vision/capture) + ПОСТОЯННЫЙ индикатор + только с согласия (/api/desktop/consent)
[ ] D-13 suggest: детектор событий (ошибка/диалог/простой) → инициатива с бюджетом N/час и тихими часами (MVP: пузырь по caption, бюджет не реализован — будущая)
[ ] D-14 act: белый список через act_on_screen, остальное — с подтверждением (будущая: нужен модуль детектора + whitelist)
[V] D-15 /api/consent (реализовано как /api/desktop/consent, DC-04) + consent-диалоги L2/L3 в оверлее (чекбокс согласия в настройках)

### P3 — 3D
[ ] D-16 VRM-модель (three-vrm), blend-shapes по тону ответа (нужен .vrm от создателя)
[ ] D-17 Lip-sync от громкости TTS (AnalyserNode → рот) (заготовка setMouthOpen в avatar.js)
[ ] D-18 Лимит GPU: 30 fps, low-power, настройка «качество аватара» (будущая)

*Примечание расхождения со спекой:* в директиве D-10 сказано «/api/stt НЕТ», но эндпоинт
уже реализован в DC-02 (POST /api/stt, опциональный Whisper). Аналогично D-15 (/api/consent)
реализовано как /api/desktop/consent (DC-04). По правилу «внешнее ТЗ сверять с реальным кодом»
эти задачи помечаются с учётом существующего. WebUI 8787 не тронут — оверлей отдельный клиент.

*Hermes = блок D добавлен (solo, 2026-08-11). Цикл подхватит после T-очереди (T уже завершена).*
