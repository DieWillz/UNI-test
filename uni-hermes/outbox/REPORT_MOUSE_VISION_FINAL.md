# REPORT_MOUSE_VISION_FINAL — консолидация мыши и visual_action

Дата: 2026-08-12 (ночь). Исполнитель: Hermes (SOLO, координатор спит).
Ветка: `night/uni-mouse-vision`, коммит `76f23ca`.

## Реальный аудит (ЭТАП 1) — что УЖЕ было в коде
Большинство ЭТАПОВ 1-4 **уже реализовано в прошлые ночи** (N-04..N-10, B-01..B-08,
зафиксировано в `UNI_NIGHT_LOG.jsonl`). Проверка кода подтверждает:

| Требование PLAN | Статус | Где |
|----------------|--------|-----|
| `computer.py` use_human_motion + fallback pyautogui | ✅ ЕСТЬ | `uni/capabilities/computer.py:42,52,60` |
| `HumanMouseController` интегрирован | ✅ ЕСТЬ | `computer.py:25,54` (откат на pyautogui при сбое) |
| `motion/driver.py` сохранён (НЕ удалён) | ✅ ЕСТЬ | `uni/motion/driver.py` (6872 б) |
| `act_on_screen(goal, max_steps)` в `visual_action.py` | ✅ ЕСТЬ | `uni/tools/visual_action.py:90` |
| Замкнутый цикл: analyze→click→verify | ✅ ЕСТЬ | `visual_action.py:201,239` (повторный analyze_desktop) |
| BLACKLIST + fail-closed | ✅ ЕСТЬ | `visual_action.py:26,113` (format/delete/shutdown/regedit) |
| СТОП-сигнал для act_on_screen | ✅ ЕСТЬ | `visual_action.py:62,66,125` (request_stop) |
| WebUI кнопка СТОП + лог шагов | ✅ ЕСТЬ | `index.html:72,90` (emergencyStop), server.py `/api/desktop/act` (D-14:1291), `request_stop` в server.py:1925 |
| Тесты human_mouse импортируют HumanMouseController | ✅ ЕСТЬ | `tests/test_human_mouse.py:116,138,152,163` |

## Что СДЕЛАНО в этой сессии
1. **ЭТАП 2.2**: `uni/motion/driver.py` помечен DEPRECATED-заголовком
   (функционал перенесён в human_motion/human_mouse; не удалён).
2. **GITHUB-PUBLISH**: репо PUBLIC, ссылка записана в `uni-hermes/outbox/GITHUB_LINK.md`.
3. **ЭТАП 1.3 / 5.1**: pytest (релевантные) 45 passed, 0 failed;
   `check_architecture --strict` 0/0.
4. **Heartbeat**: запись в `UNI_NIGHT_LOG.jsonl` (2026-08-12T15:05).
5. **Зеркало**: `driver.py` скопирован в `UNI-mcp-server/uni/motion/`.

## Тесты (proof)
```
pytest tests/test_human_mouse.py tests/test_visual_action_loop.py \
       tests/test_motion_trajectory.py tests/test_event_loop_visual_route.py \
       tests/test_local_vision_fallback.py tests/test_vision_russian.py
-> 45 passed, 2 warnings (pydantic-deprecation, не мои), 0 failed

scripts/check_architecture.py --strict -> Summary: 0 error(s), 0 warning(s)
```

## Pre-existing баги (честно, НЕ чинил)
- `tests/fasttrack/test_camera.py::test_camera_starts_without_notice` — падает
  (CameraCapability.start(notice_ack=False) -> success=False). Код camera я не трогал.
- `tests/fasttrack/test_realtime_role.py::test_role_loads_independently_of_cwd` —
  падает (роль xtoys_mistress теперь "Dorch", не "Госпожа" — тест устарел).
  **XToys — запретная зона**, править не стал. Требует отдельной задачи/ADR.

## Статус SNAPSHOT.txt
Файл `SNAPSHOT.txt` не найден в корне (возможно, в UNI-mcp-server). Актуальный
коммит зафиксирован: `76f23ca` (2026-08-12). Состояние синхронизировано с origin
(ahead/behind 0/0).

## Что НЕ делал (риски)
- Не переписывал `index.html` (виджет лога шагов act_on_screen) — СТОП и лог уже
  есть (B-01), риск сломать v2.7/v2.8 админку.
- Не трогал `motion/driver.py` логику (только DEPRECATED-комментарий).
- Не коммитил чужие deletions `.uni-yandex-council-profile/...` (вне scope).

## Итог
Замкнутый контур визуального управления ПК (вижу→решаю→кликаю→проверяю) УЖЕ
рабочий в каноне. Моя сессия: довела до чистоти (DEPRECATED), доказала тестами,
опубликовала ссылку для ревью другими ИИ. Готова к проверке координатором.
