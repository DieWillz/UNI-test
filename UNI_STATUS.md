# UNI — актуальное состояние

Срез: **2026-09-10**. Канонический проект: `C:\LLM\UNI`, ветка `Codex-17aug`.
Статусы основаны на свежем аудите кода и тестах; старые результаты 2026-08-13 больше не считать текущим baseline.

## Краткий итог

UNI уже имеет сильную основу автономного оператора: canonical contracts, Action Registry, Mission Planner, Mission Executor, независимую verification-модель, Browser/Windows providers, Vision, Speech, Dorch ControlQueue, WebUI и Remote-слой.

Инженерная оценка зрелости: функциональная полнота порядка **70–80%**, готовность как надёжного автономного продукта порядка **50–60%**. Главная проблема сейчас не отсутствие модулей, а несколько параллельных execution-paths и недостаток живых E2E-сценариев.

## Свежие проверки 2026-09-10

- `pytest --collect-only -q` → **664 tests collected**.
- `python -m uni.check_architecture --strict` → **0 errors, 0 warnings**.
- Полный suite до последних UI-фиксов: **656 passed, 3 skipped, 5 failed, 7 subtests passed**; процесс завершился штатно без прежнего `Tcl_AsyncDelete` crash.
- После исправлений config/TTS/chat/camera targeted suite → **21 passed**.
- Новый admin-config suite → **8 passed**.
- Реальный Playwright config-editor E2E → **1 passed**.
## Что реализовано

| Подсистема | Текущее состояние |
|---|---|
| Contracts / TaskOutcome / Verification | Реализовано; VERIFIED требует evidence |
| Action Registry | Реализован; browser/computer/camera/speech/vision/xtoys/operator/file actions |
| Mission Planner | Реализован; JSON-планы, зависимости, postconditions, registered actions only |
| Mission Executor | Реализован; observe → execute → re-observe → verify → retry/replan |
| Independent Verifier | Реализован; DOM/UIA/window/file/download/session evidence |
| Browser Operator | Зрелый код, требуется больше live SPA/modal/upload/download E2E |
| Windows/UIA | Запуск приложений, мышь/клавиатура, clipboard, UIA tree/read/set; нужен multi-app E2E |
| Speech | faster-whisper + Silero/Piper, mixed input, interruptible playback; реальный whisper E2E ещё нужен |
| Vision | screen/file/desktop analysis, compare/diff, VLM integration; использовать как fallback |
| Dorch | Coordinator + ControlQueue + Intiface + autonomous paths; есть lifecycle debt |
| WebUI | Рабочая единая админка, но `server.py` остаётся крупным legacy-монолитом |
| Remote/mobile | Контракты и UI есть; нужен реальный phone/auth/reconnect E2E |
| Telegram | Adapter/transport слой есть; полноценный runtime polling/webhook ещё не закончен |
| Packaging | runtime/launcher есть; законченного installer/portable артефакта нет |

## Архитектура зрения

Канонический порядок восприятия интерфейса: **DOM/UIA → OCR → дешёвая visual verification/diff → VLM/Vision fallback**.

OCR не заменяет Vision. OCR отвечает за текст, а VLM нужен для иконок без подписей, изображений, пространственных отношений, визуальных состояний и общего смысла сцены. VLM не должен запускаться на каждом кадре, если DOM/UIA/OCR уже дают достаточное наблюдение.
## Админка `config.yaml`

Добавлен schema-driven редактор настроек:

- backend: `uni/webui/config_admin.py`;
- API: localhost-only `GET/POST /api/admin/config`;
- frontend: `uni/webui/js/settings.js` + `uni/webui/css/settings.css`;
- форма строится по реальной Pydantic-модели `Config`, а не дублирует YAML вручную;
- секреты write-only и не возвращаются открытым текстом;
- неизвестные поля отклоняются;
- `agent.verification_enabled` read-only и не может быть выключен из UI;
- весь новый config валидируется до записи;
- запись выполняется атомарно;
- поля помечаются как runtime/restart-required;
- текущий Dorch max-intensity синхронизируется с живым runtime.

Через интерфейс доступны основные параметры LLM, Browser, Computer, Camera, STT/TTS, OCR/Vision, Dorch, Agent, Autonomous, Memory, Logging, Council, Context и диагностики. Старый `/api/config` сохранён для совместимости.

## Текущие P0/P1 риски

1. **Единый execution pipeline ещё не завершён.** Side effects могут идти через Operator, DirectCommand/ToolExecutor, VisualActionAgent, `_free_form()`, AutonomousController и Dorch paths с разной строгостью verification.
2. **ControlQueue lifecycle:** ранее воспроизведены ошибки manual takeover и STOP/reset с реальным `ToyControlCoordinator` + fake bridge; они требуют отдельной интеграционной фиксации и проверки.
3. `remove_pending` в ControlQueue требует отдельного regression test по production path.
4. Telegram retry test остаётся известным красным/неоднозначным контрактом; нужно определить владельца retry/backoff.
5. General Autonomous Runtime ещё не сведен к одному циклу Operator: OBSERVE → PLAN → ACT → VERIFY → RECOVER → CONTINUE.
6. Screen Watch использует слишком грубую change-detection логику; нужны ROI/debounce/significance thresholds и DOM/UIA-first perception.
7. Живые hardware E2E для микрофона, камеры и Intiface/device остаются обязательными до product-ready статуса.

## Multi-agent состояние

Рабочее дерево активно изменяется несколькими агентами. Не использовать destructive git-команды и не считать неизвестные dirty changes своими. Перед редактированием проверять `git status` и diff конкретных файлов. Канонический автоматизированный MAWC/resource-lease слой уже начал появляться в `uni/devcoord`, но его внедрение ещё продолжается.
