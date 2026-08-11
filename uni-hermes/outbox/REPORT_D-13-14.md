# ОТЧЁТ: D-13 + D-14 — Проактивность (suggest / act)
Дата: 2026-08-11
Задача: D-13 (детектор событий + бюджет) и D-14 (act whitelist через act_on_screen).
Режим: NIGHT SOLO, прямая работа в каноне.

## Что сделано (факт)
- **D-13** Создан `uni/desktop/observe.py` — модуль проактивности:
  - `detect_event(caption)` — эвристика (error/dialog/idle по ключевым словам).
  - `budget_ok(limit_per_hour)` — бюджет инициатив N/час + тихие часы (23:00–07:00).
  - `suggest(caption)` — возвращает {initiative, event, text, reason}.
  - Добавлен эндпоинт `POST /api/desktop/suggest` в server.py (аддитивно).
- **D-14** В `observe.py`: `ACTION_WHITELIST` (open_app/click_ok/type_text/scroll_down/minimize)
  + `act_allowed(action)`. Эндпоинт `POST /api/desktop/act` в server.py:
  - неизвестное действие → 403 с перечнем разрешённых;
  - разрешённое → вызов `agent.act_on_screen(action, param)` (если агент и метод доступны).

## Файлы изменены/созданы
- `uni/desktop/observe.py` (новый модуль)
- `uni/webui/server.py` (аддитивно: `/api/desktop/suggest`, `/api/desktop/act`)
- `tests/test_desktop_proactive.py` (новый, 4 passed)
- `UNI_BACKLOG.md` (D-13/D-14 → [V])
- `uni-hermes/outbox/REPORT_D-13-14.md` (этот отчёт)

## Тесты (proof of work)
- `tests/test_desktop_proactive.py` → **4 passed** (unit: detect_event, act_whitelist;
  integration через реальный сервер: suggest возвращает event, act→403 для неизвестного).
- Полный сьют канона: **77 passed** (B+T+DC+D), 0 failed; check_architecture 0/0.

## Соблюдение запретов
- WebUI 8787 НЕ тронут (эндпоинты аддитивны). Файлы не удалены. config/XToys/Intiface/порты не тронуты.
- Без заглушек: D-16..D-18 (3D) оставлены [ ] (нужен .vrm-ассет от создателя + three-vrm).

## Визуальный эффект (для координатора)
При включённом согласии наблюдения оверлей раз в 10с делает скриншот → /api/vision/capture →
caption. Если caption похож на ошибку/диалог (D-13), и бюджет не исчерпан и не тихие часы —
Юни показывает пузырь-инициативу («Вижу ошибку, помочь?»). Уровень act (D-14) позволяет
оверлею выполнять только безопасные действия из белого списка через act_on_screen.

## Замечание
Реальное выполнение act_on_screen требует живого агента (грузит LLM/модель) — в тесте не
вызываем, чтобы не висеть; whitelist-логика покрыта юнит-тестом.

## Следующая задача
D-16..D-18 (3D VRM/lip-sync/GPU) — требуют ассет .vrm от создателя. Очередь D-01..D-15 выполнена
(P0/P1/P2), кроме D-16..D-18 (честно [ ]).

---
Hermes = 2026-08-11 (SOLO, прямая работа в каноне).
