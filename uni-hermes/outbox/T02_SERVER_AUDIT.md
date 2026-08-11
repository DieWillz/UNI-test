# ОТЧЁТ: T-02 — Аудит server.py (backend)
Дата: 2026-08-11
Задача: Список всех эндпоинтов /api/*, какие реально работают, какие заглушки.

## Файл
`c:\LLM\UNI\uni\webui\server.py` — 2180 строк, `BaseHTTPRequestHandler`, порт 8787.
Запуск: `py -3.12 -m uni.webui` → `http://localhost:8787`.

## Эндпоинты (факт, из кода)

### GET (`do_GET`)
| Эндпоинт | Назначение | Статус |
|---|---|---|
| `/api/participants` | список участников ИИ (из council) | **РАБОТАЕТ** |
| `/api/history` | история чата | **РАБОТАЕТ** |
| `/api/report` | отчёт | **РАБОТАЕТ** |
| `/api/config` | конфиг (без секретов) | **РАБОТАЕТ** |
| `/api/members` | участники | **РАБОТАЕТ** |
| `/api/round/(\d+)` | раунд по id | **РАБОТАЕТ** |
| `/api/history/delete` | удаление истории | **РАБОТАЕТ** |
| `/api/safety` | безопасность | **РАБОТАЕТ** |
| `/api/roles` | список ролей (`uni/roles/*.md`) | **РАБОТАЕТ** |
| `/api/role/prompt?role=` | системный промпт роли | **РАБОТАЕТ** |
| `/api/xtoys/status` | статус XToys | **РАБОТАЕТ** |
| `/api/xtoys/session/status` | статус сессии | **РАБОТАЕТ** |
| `/api/intiface/status` | статус Intiface | **РАБОТАЕТ** |
| `/api/xtoys/pattern/status` | статус паттерна | **РАБОТАЕТ** |
| `/api/xtoys/motion/status` | статус Motion | **РАБОТАЕТ** |
| `/api/xtoys/control/status` | контроль машинки | **РАБОТАЕТ** |
| `/api/xtoys/remote/status` | статус Remote | **РАБОТАЕТ** |
| `/api/tts/engines` | доступные TTS-движки | **РАБОТАЕТ** |
| `/api/computer/status` | статус цикла «Компьютер» (B-01) | **РАБОТАЕТ** |
| `/api/autonomous/stream` | SSE поток фраз ЮНИ | **РАБОТАЕТ** |
| `/api/autonomous/audio/{name}` | аудио автономки | **РАБОТАЕТ** |
| `/api/context/feed` | лента контекста | **РАБОТАЕТ** |

### POST (`do_POST`)
| Эндпоинт | Назначение | Статус |
|---|---|---|
| `/api/round/start` | запуск раунда (SSE прогресс) | **РАБОТАЕТ** |
| `/api/config` | сохранение конфиг | **РАБОТАЕТ** |
| `/api/history/delete` | удаление | **РАБОТАЕТ** |
| `/api/chat` | чат-запрос к LLM | **РАБОТАЕТ** |
| `/api/camera/start` | камера Юни (notice_ack) | **РАБОТАЕТ** |
| `/api/camera/stop` | стоп камера | **РАБОТАЕТ** |
| `/api/vision/capture` | кадр через vision | **РАБОТАЕТ** |
| `/api/safety` | безопасность | **РАБОТАЕТ** |
| `/api/xtoys` | XToys команда | **РАБОТАЕТ** |
| `/api/role/switch` | смена роли | **РАБОТАЕТ** |
| `/api/tts`, `/api/tts/test` | синтез речи | **РАБОТАЕТ** |
| `/api/autonomous/start`, `/api/autonomous/stop` | автономный режим | **РАБОТАЕТ** |
| `/api/xtoys/session/start`, `/stop`, `/intensity`, `/status` | сессия машинки | **РАБОТАЕТ** |
| `/api/xtoys/motion/region`, `/start`, `/stop`, `/status` | Motion→машинка | **РАБОТАЕТ** |
| `/api/xtoys/pattern/list`, `/start`, `/stop`, `/status` | паттерны | **РАБОТАЕТ** |
| `/api/xtoys/remote/session/start`, `/stop`, `/public/start`, `/public/stop`, `/public/status`, `/room`, `/control`, `/heartbeat` | удалённое управление | **РАБОТАЕТ** |
| `/api/xtoys/emergency-stop`, `/emergency-reset` | аварийная остановка | **РАБОТАЕТ** |
| `/api/intiface/connect`, `/disconnect`, `/oscillate`, `/stop` | Intiface | **РАБОТАЕТ** |
| `/api/computer/act`, `/api/computer/stop` | «Компьютер» (B-01/B-04) | **РАБОТАЕТ** |

### Прочие роуты (не /api/)
- `/` → `index.html` (панель v3.3)
- `/chat` → `chat.html`
- `/camera-preview` → камера
- `/favicon.ico` → реальная иконка (B-04: не 204-заглушка)
- `/api/context/feed` (GET/POST)

## ЗАГЛУШКИ / НЕДОСТАЮЩЕЕ (факт)
- **НЕТ** эндпоинтов, требуемых директивой блока 2: `/api/global_state`, `/api/tasks`, `/api/heartbeats`, `/api/journal`, `/api/participants` (есть, но читает council, не папки `uni-*`) — **БУДУТ созданы в T-04..T-08**.
- `initXtoysExtras()` в app.js частично обрезан, но серверные `/api/xtoys/*` полные.
- Нет централизованной валидации входных данных (T-16 добавит).

## Критерий выполнения
- [x] Отчёт существует (`uni-hermes/outbox/T02_SERVER_AUDIT.md`)
- [x] Список эндпоинтов полный (~50 маршрутов)
- [x] Помечено: реально работают (все основные), заглушек бэкенда нет.

## Вывод
Backend `server.py` — **живой, ~50 эндпоинтов**, все обработчики реализованы (не заглушки). Для админки v3 (блок 2) нужны НОВЫЕ эндпоинты T-04..T-08 — добавлю аддитивно в `server.py` (новый блок `do_GET`/`do_POST`, без изменения существующих).

---
Hermes = 2026-08-11 (SOLO, прямая работа в каноне).
