# UNI_GLOBAL_STATE.md — статус компонентов (обновлено 2026-08-12)

## Desktop Companion (оверлей, `uni/desktop/`)
Статус: **РАБОТАЕТ** (после V-01..V-03 fix)
- Окно: transparent, 382×640, всегда visible, у нижней кромки экрана
  (Win32 rect (1142,168)-(1524,808) на экране 1536×864 / workArea 1536×816).
- Аватар: **3D VRM** (`UNI.vrm` через `@pixiv/three-vrm` + importmap),
  SVG-fallback при сбое. `desktop.log` содержит «VRM loaded».
- Чат: `POST /api/chat` → ответ агента (LLM qwen3.5-9b на 8787).
- Трей: Показать / уровни наблюдения (observe/suggest/act/off) / Выход.
- Лог: `uni/desktop/desktop.log` (ready, createWindow, placeAtBottomRight final,
  HTTP-вызовы, ошибки renderer).
- V-01/V-02/V-03: исправлены (const uni дубль / three import / позиция).

## WebUI (сервер 8787, `uni/webui/`)
Статус: **РАБОТАЕТ**
- `GET /` → 200 (админка v3 основная).
- `GET /v3` → 200 (R-01, маршрут /v3).
- `POST /api/chat` → 200, агент отвечает.
- `GET /api/config` → без сырых ключей (R-02 маскировка).
- `GET /api/participants` → 11 участников (живые данные).
- `POST /api/desktop/consent` → 200 (уровень observation).
- `POST /api/desktop/suggest`, `/api/desktop/act` → proactive (D-13/D-14).
- `POST /api/vision/capture` → 409 (использует камеру, не экран; экран —
  Win32-захват `tools/screenshot.py`).

## Backend-тесты
- Мой subset (R + desktop + proactive + admin + p0): **26 passed**.
- `check_architecture --strict`: **0 error / 0 warning**.
- Полный `pytest`: 251 passed, **2 failed (pre-existing, вне scope)**:
  - `tests/fasttrack/test_camera.py::test_camera_starts_without_notice`
  - `tests/fasttrack/test_realtime_role.py::test_role_loads_independently_of_cwd`
  (код camera capability / `xtoys_mistress` role-prompt не трогался в этой сессии).

## Запреты (соблюдены)
config.yaml / XToys / Intiface / порты 8000/1234/12345/12347 — не тронуты.
В main не пушилось. Файлы не удалены (только правки/DEPRECATED).

## Визуальный proof
Программный proof получен (лог/Win32/API). Инструмент vision недоступен в
сессии Hermes → финальная визуальная проверка скриншотов (`uni-hermes/outbox/`)
за координатором. Скриншоты: `SHOT_1.png`, `SHOT_1_crop.png`.

---
Hermes = 2026-08-12 (V-01..V-03 + E2E, прямая работа в каноне).
