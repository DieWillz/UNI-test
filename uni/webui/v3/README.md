# UNI Admin v3 — консоль роя

Минималистичная админка для наблюдения за состоянием проекта UNI и участниками (ИИ-роем).
Создана рядом с основной панелью `uni/webui/index.html` (v3.3) — её не дублирует и не заменяет.

## Запуск
Сервер панели (`uni/webui/server.py`, порт 8787) уже отдаёт статику. Чтобы открыть v3:
```
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -m uni.webui
# затем браузер: http://127.0.0.1:8787/v3/index.html
```
> Примечание: backend отдаёт `style.css`/`app.js` через `static_aliases`, но маршрут
> `/v3/` не замаплен явно. Если `/v3/index.html` не открывается — откройте
> `index.html` напрямую из `uni/webui/v3/` (относительные ссылки на `favicon.ico` и
> `style.css`/`app.js` рядом с файлом).

## Страницы
- **Главная** — `GET /api/global_state` (сводка `UNI_GLOBAL_STATE.md`) + `GET /api/heartbeats` (статус участников 🟢/🔴), авто-обновление 30s.
- **Задачи** — `GET /api/tasks` (парсинг `UNI_BACKLOG.md`, таблица со статусами).
- **Участники** — `GET /api/participants_dirs` + `/api/heartbeats` (карточки).
- **Журнал** — `GET /api/journal` (последние 100 записей `UNI_JOURNAL.jsonl`).
- **Настройки** — read-only (config.yaml не трогаем по правилам).

## Безопасность
- Кнопка **СТОП** (в шапке) → `POST /api/admin/stop` → создаёт `C:\LLM\UNI\STOP.txt`. Все агенты останавливаются.
- Все чтения файлов защищены `is_relative_to(_ROOT)` (path traversal невозможен).
- `config.yaml` не отображается и не редактируется (секрет).

## Тесты
```
PYTHONPATH=C:\LLM\UNI UNI_NO_DISPLAY_CALIBRATION=1 C:\LLM\python312\python.exe -m pytest tests/test_api_admin_v3.py -q
```
8 passed (реальный HTTP-сервер в потоке).

---
Hermes = 2026-08-11 (SOLO).
