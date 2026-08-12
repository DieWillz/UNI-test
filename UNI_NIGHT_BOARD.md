# UNI NIGHT BOARD — тандем Hermes + Юни

Дата ночи: 2026-08-10
Координатор: человек (ушёл спать)
Исполнители: Hermes (код/интеграция), Юни (координация/контроль/отчёт)
Режим: автономная ночная работа над «физическая мышь + компьютерное зрение»

## Цель ночи
Довести физическую мышь и компьютерное зрение UNI до рабочего замкнутого контура (вижу→решаю→кликаю→проверяю).

## Минимальный результат к утру
1. HumanMouseController подключён к computer.py как опция use_human_motion.
2. pyautogui сохранён как fallback.
3. motion/driver.py помечен deprecated (не удалён).
4. test_human_mouse исправлен или корректно помечен integration.
5. check_architecture --strict проходит.
6. Есть базовый visual action loop (uni/tools/visual_action.py) с mock-тестом.
7. Есть ночной отчёт и метрики.

## Запрещено (ночью)
- трогать config.yaml;
- трогать процессы, порты 8000 и 8787;
- трогать XToys/Intiface/устройства (отдельный L4-контур);
- удалять файлы без переноса;
- пушить в main (только в night/uni-mouse-vision);
- писать успех без доказательств;
- симулировать heartbeat;
- выполнять опасные системные команды (format/del/rm/reg/shutdown).

## Кто что делает
- Hermes: ветка night/uni-mouse-vision, правит код, тесты, коммиты, proof, лог.
- Юни: контекст, locks, journal, метрики, критика, утренний отчёт.

## Задачи
| ID | Задача | Владелец | Статус |
|----|--------|----------|--------|
| N-00 | Фиксация старта + ветка | Hermes | pending |
| N-01 | Подтверждение правил Hermes | Hermes | pending |
| N-02 | Аудит фактического состояния | Юни | pending |
| N-03 | Контекст для Hermes | Юни | pending |
| N-04 | Подключение HumanMouseController | Hermes | pending |
| N-05 | Разбор дубля motion/driver.py | Hermes | pending |
| N-06 | Починка test_human_mouse | Hermes | pending |
| N-07 | Замкнутый цикл visual_action | Hermes+Юни | pending |
| N-08 | Mock-тест цикла | Hermes+Юни | pending |
| N-09 | check_architecture + pytest | Hermes | pending |
| N-10 | Утренний отчёт + метрики | Юни | pending |

---
*Hermes = ночная доска от 2026-08-10.*

## FIX-AUDIT (2026-08-12) — внешний аудит ветки night/uni-mouse-vision
Режим: починка по аудиту. Статус каждого пункта (верификация → фикс).
См. uni-hermes/outbox/AUDIT_VERIFICATION.md и REPORT_FIX_AUDIT.md.

| ID | Пункт | Верификация | Статус | Коммит |
|----|-------|-------------|--------|--------|
| P1 | Мёртвая логика `_locate()` | ПОДТВЕРЖДЁН | FIXED (A-01) | 43f6431 |
| P2 | Рассинхрон порогов уверенности | ПОДТВЕРЖДЁН | FIXED (A-02) | 896d55f |
| P3 | Консолидация мыши (фасад) | ПОДТВЕРЖДЁН | FIXED (A-03) | 1c03098 |
| P4 | SmoothMouseDriver.cancel() заглушка | ПОДТВЕРЖДЁН | FIXED (A-04, в A-03) | 1c03098 |
| P5 | Нет независимого гейта (CI + импорты) | ЧАСТИЧНО | FIXED (A-05) | (см. ниже) |

Итог: 4 подтверждённых пункта + 1 частичный — все починены.
check_architecture 0/0. pytest (аудит-набор): 34 passed.
Pre-existing (НЕ чинились, вне scope): test_camera (notice_ack),
test_realtime_role (xtoys "Dorch" — запретная зона).
