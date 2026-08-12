# ОТЧЁТ: R-01 + R-02 — маршрут /v3 и маскировка ключа OpenRouter
Дата: 2026-08-12
Задача: R-01 (маршрут /v3), R-02 (маскировать ключ OpenRouter в UI).
Режим: прямая работа в каноне.

## R-01 — маршрут /v3
Добавлен в `do_GET` server.py: `GET /v3` (и `/v3/`) отдаёт `uni/webui/v3/index.html`
(админка v3). Статика v3 (`/v3/app.js`, `/v3/style.css`) отдаётся существующим
блоком статики (резолвится в `uni/webui/v3/app.js`). 404 если файл отсутствует.

## R-02 — маскировка ключа OpenRouter (и любых секретов)
Диагностика: бэкенд УЖЕ не отдавал сырые ключи — `/api/config` и `/api/participants`
возвращают `api_key_set: bool`, а не значение (lines 998, 582 server.py). Фронтенды
(`js/app.js`, `remote-control.html`) нигде не рендерят сырой ключ.
Для defense-in-depth добавлена рекурсивная маскировка `_sanitize_secrets(obj)`,
применяемая в `do_GET._json` ко ВСЕМ JSON-ответам:
- `_SECRET_VAL_RE` ловит `sk-...`, `gsk_...`, `AQ....`, `hf_...`, `Bearer ...`
  (case-insensitive, с учётом `-`/`_`/`A-Z`) → замена на `***masked***`.
- ключи с именем `api_key`, `secret`, `token`, `password`, `authorization` и т.п.
  тоже маскируются.
- любой вложенный dict/list обходится рекурсивно.
Это страхует на будущее: ни один эндпоинт не сможет случайно слить секрет в UI.

## Файлы изменены
- `uni/webui/server.py` (R-01: маршрут /v3; R-02: `_sanitize_secrets` + применение в `_json`)
- `tests/test_r_queue.py` (новый: 3 passed)
- `uni-hermes/logs/hrm_heartbeat.txt`

## Тесты (proof of work)
- `tests/test_r_queue.py` → **3 passed** (R-01 /v3 отдаёт HTML; R-02 маскировка sk-/gsk_/hf_/AQ.; idempotent).
- Полный сьют канона: **19 passed** (R + desktop + proactive + admin), 0 failed.
- `check_architecture --strict`: 0 error, 0 warning.
- `py_compile server.py`: COMPILE_OK.

## Соблюдение запретов
WebUI 8787 не сломан (маршрут аддитивен, маскировка не меняет логики), config.yaml/
XToys/Intiface/порты/процессы не тронуты. Файлы не удалены.

---
Hermes = 2026-08-12 (прямая работа в каноне, R-01/R-02).
