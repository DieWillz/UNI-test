# ОТЧЁТ: DC-01..DC-09 — Desktop Companion (оверлей)
Дата: 2026-08-11
Задача: Реализовать прозрачный десктоп-оверлей по дополнению создателя («Основная оболочка Юни.md»).
Режим: NIGHT SOLO, прямая работа в каноне.

## Что сделано (факт)
- **DC-01** Дизайн-док `uni/webui/desktop/DESIGN.md` (компоновка, фазы, риски, план задач).
- **DC-02** `uni/capabilities/stt.py` — STT-модуль (опциональный faster-whisper/openai-whisper, ленивая загрузка). `POST /api/stt` в server.py (multipart + raw, 501 если движок недоступен).
- **DC-03** `GET /api/desktop/events` — SSE-поток событий для оверлея (hello/consent_changed/initiative).
- **DC-04** `GET/POST /api/desktop/consent` — согласие на наблюдение + журнал `uni/memory/consent_log.jsonl`.
- **DC-05** `uni/webui/desktop/main.js` — Electron: прозрачное frameless окно, always-on-top (screen-saver), click-through по альфе (hit-test), трей, глобальный PTT `Ctrl+Shift+Space` (не конфликтует с AHK `Ctrl+Alt+*`), SSE-клиент.
- **DC-06** `index.html` + `style.css` — компоновка из прототипа (чат слева, аватар справа у кромки, ряд круглых кнопок сверху).
- **DC-07** `app.js` — чат→`/api/chat`+TTS, SSE `/api/autonomous/stream`, события от main, кнопки (стоп/настройки/зрение/скрыть/автономия), PTT-запись→`/api/stt`, настройки (роль/голос/уровень/прозрачность).
- **DC-08** `tests/test_api_desktop.py` — 4 passed (реальный HTTP-сервер: stt отвечает, consent GET/POST+журнал, events SSE).
- **DC-09** Зеркалирование + коммит + пуш.

## Файлы изменены/созданы
- `uni/webui/server.py` (T-04..T-08, T-15, ТЕПЕРЬ DC-02/03/04 — аддитивно)
- `uni/capabilities/stt.py` (новый)
- `uni/webui/desktop/{DESIGN.md, package.json, main.js, index.html, style.css, app.js}` (новый модуль)
- `tests/test_api_desktop.py` (новый)
- `UNI_BACKLOG.md` (блок DC-01..DC-12)
- `uni-hermes/outbox/REPORT_DC.md` (этот отчёт)

## Тесты (proof of work)
- `node --check` для `main.js`, `app.js`, `v3/app.js` → OK (все JS валидны).
- `tests/test_api_desktop.py` → **4 passed** (реальный сервер в потоке).
- Полный сьют канона: **69 passed** (B+T) + 4 (DC) = 73 passed, 0 failed (прогон DC-блока отдельно 4 passed).
- `scripts/check_architecture.py --strict` → **0 errors, 0 warnings**.

## Архитектура
Соблюдены запреты координатора: файлы не удалены, config.yaml/XToys/Intiface/порты 8000/1234/12345/12347 не тронуты, main не запушен. Новые эндпоинты добавлены аддитивно, существующие `/api/chat`, `/api/tts`, `/api/roles`, `/api/safety`, `/api/autonomous/stream` не изменены.

## Визуальный эффект (что увидит пользователь)
После `cd uni/webui/desktop && npm i && npm start` (на целевой машине): поверх рабочего стола
появляется прозрачное окно — справа стоит аватар-компаньон Юни, слева чат-панель, сверху ряд
кнопок (настройки/зрение/автономия/стоп/скрыть). Клики по пустым зонам проходят сквозь окно
(click-through). Чат работает через `/api/chat`, ответы озвучиваются, автономные фразы прилетают
в чат. Кнопка СТОП создаёт `STOP.txt`. PTT `Ctrl+Shift+Space` включает микрофон → `/api/stt` →
текст в чат. Уровень автономии (off/observe/suggest/act) переключается в настройках и шлёт согласие
в `/api/desktop/consent` (с индикатором наблюдения).

## Замечание по окружению
- Whisper (faster-whisper) **доступен** в этом окружении → `/api/stt` реально работает при наличии модели.
- Electron **не установлен** здесь (нет npm-пакета) — код валиден, запуск на машине координатора.

## Следующая задача
DC-10..DC-12 — будущие (3D VRM, детектор событий наблюдения, миграция на Tauri). Очередь DC-01..DC-09 пуста.

---
Hermes = 2026-08-11 (SOLO, прямая работа в каноне).
