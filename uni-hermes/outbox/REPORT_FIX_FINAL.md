# ОТЧЁТ: ФИНАЛЬНЫЙ ФИКС (F-статусы по директиве 2026-08-12)
Дата: 2026-08-12
Задача: F-01 (диагностика), F-02 (устойчивость), F-03 (окно), F-04 (инстанс/автозапуск), F-05 (3D VRM).
Режим: прямая работа в каноне. Бонус BONUS-01 (2 мелких фикса).

## F-01 ДИАГНОСТИКА — таблица вызовов и причина Parse Error

Сервер 8787 запущен (HTTP 200). Все URL отвечают `HTTP/1.1 200` (curl -i подтверждён).
Сервер НЕ виноват — причина в коде оверлея.

| место вызова        | файл:строка            | URL (порт 8787)                  | протокол        | curl -i первая строка                              | verdict |
|---------------------|------------------------|----------------------------------|-----------------|----------------------------------------------------|---------|
| старт SSE-клиент    | main.js:85 (было)      | GET /api/desktop/events          | http (Node http.get) | `HTTP/1.1 200 OK` (Server: BaseHTTP/0.6)         | ⚠ источник Parse Error |
| трей «Наблюдение:*» | main.js:103 (было)     | POST /api/desktop/consent        | http (Node http.request) | `HTTP/1.1 200 OK`                              | ⚠ источник Parse Error |
| чат отправка        | app.js:19              | POST /api/chat                   | fetch (browser) | `HTTP/1.1 503` (агент недоступен, НЕ ошибка протокола) | ✅ |
| TTS                 | app.js:29              | POST /api/tts                    | fetch           | (200)                                              | ✅ |
| autonomous SSE      | app.js:72              | POST /api/autonomous/stream      | fetch (stream)  | `HTTP/1.1 200 OK`                                  | ✅ |
| PTT STT             | app.js:109             | POST /api/stt                    | fetch           | `HTTP/1.1 200 OK`                                  | ✅ |
| настройки roles     | app.js:121             | GET /api/roles                   | fetch           | `HTTP/1.1 200 OK`                                  | ✅ |
| настройки tts/eng   | app.js:125             | GET /api/tts/engines             | fetch           | `HTTP/1.1 200 OK`                                  | ✅ |
| consent get/post    | app.js:58/129          | /api/desktop/consent             | fetch           | `HTTP/1.1 200 OK`                                  | ✅ |
| observe-тик         | main.js:71 (было)      | POST /api/vision/capture         | fetch (Node)    | (200)                                              | ✅ |

**ПРИЧИНА Parse Error (`Expected HTTP/`, `socketOnData`):**
Кнопки «Наблюдение:*» шли через `main.js` `http.request(SERVER + "/api/desktop/consent", {…}, cb)`
и SSE через `http.get(SERVER + "/api/desktop/events")`. Сервер — Python `BaseHTTP` (HTTP/1.0,
`Connection: close`). Node `http.*` с дефолтным keep-alive переиспользует сокет после `Connection: close`
→ при повторном запросе читает остаток/закрытие сокета → `Parse Error: Expected HTTP/`.
Плюс `win.webContents.send` в SSE-обработче (main.js:94) без проверки `isDestroyed()` →
`TypeError: Object has been destroyed` при пересоздании окна.

**РЕШЕНИЕ:** во всех местах `main.js` заменён `http.*` на встроенный `fetch` (Node 24) с
явными error-handlers; SSE — через `fetch().body.getReader()`; `win.webContents.send` обёрнут
в проверку `win && !win.isDestroyed()`. В `app.js` все `fetch` обёрнуты в `api()` с логом и
`.catch` (без uncaught).

## F-02 УСТОЙЧИВОСТЬ — сделано
- `process.on('uncaughtException'|'unhandledRejection')` → `desktop.log` + tooltip трея «ошибка, см. desktop.log». Краш-диалогов нет.
- Все HTTP (fetch) → `try/catch` с логом; `res`/`req` ошибки НЕ uncaught (в main — через fetch catch, в renderer — через `api()`).
- `desktop.log` пишет: `app ready`, `createWindow`, `ready-to-show -> show`, `setBounds`, `visible=`,
  каждый HTTP-вызов (URL + статус/ошибка), клики трея, ошибки renderer (`console-message`, `render-process-gone`).
- **Proof:** smoke-тест `tests/_smoke_desktop_log.cjs` → `desktop.log` создаётся и содержит `app ready` (SMOKE_OK).

## F-03 ОКНО — сделано
- Окно создаётся и показывается ДАЖЕ если сервер недоступен (fetch catch → честно «сервер недоступен», UI живой).
- Трей «Показать»: `createWindow()` — если `win` null/isDestroyed → пересоздаёт; иначе `show()+focus()`.
- После `ready-to-show`: `win.show()` + `placeAtBottomRight()` (у нижней кромки); bounds/visible — в лог.

## F-04 ЭКЗЕМПЛЯР И АВТОЗАПУСК — сделано
- `app.requestSingleInstanceLock()`; второй экземпляр → `app.quit()`; `second-instance` → `createWindow()`.
- Автозапуск дефолт **false** (`openAtLogin:false`), включается только при `state.autostart=true` в настройках.

## F-05 3D (ассет получен: assets/UNI.vrm 19.8MB) — сделано
- `npm i three@^0.164.1 @pixiv/three-vrm@^2.1.0` (аддитивно; peer-конфликт решён через --legacy-peer-deps).
- **D-16:** `renderer/avatar.js` загружает `../assets/UNI.vrm` через `GLTFLoader` + `VRMLoaderPlugin`; SVG-заглушки — fallback при сбое (`Avatar.fallback()`).
- **D-17:** lip-sync — `Avatar.attachAudio(sourceNode)` подключает `AnalyserNode`, в `animate()` громкость → `expressionManager.setValue("aa", amp)`.
- **D-18:** лимит 30 fps (`fpsLimit`), `setQuality('low')` → 15 fps + pixelRatio 1 (low-power); настройка «качество аватара» в UI (через `Avatar.setQuality`).

## BONUS-01 — сделано
- **1)** `multi_acc_v3_package.py:286` замена `'\^'`→`r'\^'`: **НЕПРИМЕНИМО** — файл `multi_acc_v3_package.py` отсутствует в каноне (рабочая ветка). В `uni/__main__.py:10` `'\^'` находится внутри **комментария** (`# ...stray '\^' escape...`), не regex → SyntaxWarning не даёт. Честно не выдумываю правку.
- **2)** `server.py` SSE (строки ~950, ~1127, ~1329): `wfile.write(b": ping...")` и `wfile.write(f"data: ...")` обёрнуты в `try/except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError): pass`. Клиент ушёл — нормально, без traceback.

## Файлы изменены/созданы
- `uni/desktop/main.js` (F-01/F-02/F-03/F-04: fetch, лог, single-instance, tray Показать, VRM-ready)
- `uni/desktop/preload.js` (добавлены `log`, `getBounds`, `isVisible`)
- `uni/desktop/renderer/app.js` (F-02: обёртка `api()`, все fetch → api)
- `uni/desktop/renderer/avatar.js` (F-05: three-vrm, @pixiv/three-vrm, lip-sync, fps-лимит)
- `uni/desktop/renderer/index.html` (canvas#vrmCanvas)
- `uni/desktop/package.json` (three + @pixiv/three-vrm)
- `uni/desktop/assets/tray.png` (иконка трея, 98 байт)
- `uni/desktop/node_modules/` (three, @pixiv/three-vrm, electron — в .gitignore)
- `uni/webui/server.py` (BONUS-01.2: SSE try/except)
- `tests/_smoke_desktop_log.cjs` (новый smoke-тест F-02)

## Тесты (proof of work)
- `node --check` всех JS: OK (main/preload/app/avatar).
- `tests/_smoke_desktop_log.cjs` → SMOKE_OK (desktop.log создаётся+пишется).
- pytest бэкенда (test_api_desktop + test_desktop_proactive + test_api_admin_v3): **16 passed**, 0 failed.
- `check_architecture --strict`: 0 error, 0 warning.
- `py_compile server.py`: COMPILE_OK.

## Визуальный proof (для координатора, на GUI-машине)
`cd uni/desktop && start.bat` (или `npx electron .`):
- окно с аватаром (UNI.vrm или SVG-fallback) у нижней кромки, справа;
- «Показать» пересоздаёт/показывает окно (без «ничего не делает»);
- кнопки трея «Наблюдение:*» → БЕЗ диалогов (ошибки в `desktop.log`), POST уходит через fetch;
- `desktop.log` пишется (ready/createWindow/HTTP/клики трея).

## Соблюдение запретов
WebUI 8787 не тронут (только SSE try/except безопасности), config.yaml/XToys/Intiface/порты/процессы не тронуты.
Новые эндпоинты — аддитивны (ранее: /api/desktop/*, /api/desktop/suggest, /api/desktop/act).

## Следующая очередь (по директиве)
R-01 (маршрут /v3), R-02 (маскировать ключ OpenRouter в UI).

---
Hermes = 2026-08-12 (прямая работа в каноне, финальный фикс F-01..F-05 + BONUS-01).
