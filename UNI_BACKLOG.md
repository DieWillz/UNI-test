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
