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
*Hermes = UNI_BACKLOG создан 2026-08-11 (solo, по директиве координатора).*

---
*Все задачи бэклога B-01..B-08 выполнены (solo, Hermes, 2026-08-11). Режим ожидания новых задач координатора.*
