# HERMES_UI_REPORT — Доведение desktop Юни до рабочего вида (2026-08-13, ФИНАЛ)

> Автор: Hermes (Гермес), агент-координатор Юни.
> Дата: 2026-08-13. Ветка: `clean/august-2026` (НЕ main).
> Зеркало лога: `agents/uni-hermes/HERMES_LOG_2026-08-13.md` (секция 30).

## 1. АУДИТ — какой renderer грузится

| Пункт | Действие | Фактический результат | Доказательство | Статус |
|---|---|---|---|---|
| Какой renderer | `uni/desktop/main.js:144` `loadFile(renderer/index.html)` (ui_variant=v4) | Грузится `uni/desktop/renderer/index.html` (вариант v4 — тот, что настраивал пользователь) | `main.js` строка 144 | ✅ |
| Почему «ничего не происходило» | проверка цепочки `.lnk → start_uni.bat → UNI.bat` | `UNI.bat` ранее НЕ существовал; `start.bat` ссылался на него → цепочка рвалась. Плюс `launcher.js` глушил ВСЕ серверы при флейке Electron (single-instance lock блокировал старт нового экземпляра) | `git log`, `launcher.js` до правки | ✅ найдено |
| Почему вечный спиннер | проверка `quickActionStrip` | «Юни готова» рендерилась как `action-strip` со спиннером (по директиве — пузырь БЕЗ спиннера) | `app.js` `setAction('done',...)` | ✅ найдено |
| Почему позиция неверна | проверка `placeAtBottomRight` | смешивала физические (`getBounds`) и логические (`workArea/sf`) пиксели → `y:0` (окно вверху, не над треем) | `desktop.log` `final={"x":878,"y":0}` | ✅ найдено |

## 2. ИЗМЕНЁННЫЕ ФАЙЛЫ

- `scripts/launcher.js` — рестарт Electron (до 3 попыток), `/api/launcher/stop`, гарантированный `taskkill /F /PID /T` всех детей.
- `uni/desktop/main.js` — `stopStack()` (tray «Выход»/«Стоп» → убить стек), геометрия 336×660, **фикс позиции** `placeAtBottomRight` (DIP-корректно).
- `UNI.bat` (НОВЫЙ) — единая точка входа.
- `start.bat`, `start_uni.bat` — алиасы на `UNI.bat` (DEPRECATED-шапка, не удалены).
- `uni/desktop/renderer/index.html` — логотип `brand-logo`, пустой чат `#emptyChat` + 3 чипа.
- `uni/desktop/renderer/styles.css` — `.brand-logo`, `.stop-button` (нейтральный), `.empty-chat`, `.chips`, `.ready-bubble`.
- `uni/desktop/renderer/app.js` — `initEmptyChat()`, чипы → отправка, `showReadyBubble()` без спиннера.

## 3. DEPRECATED (спорное не удалено)

- `start.bat`, `start_uni.bat` — оставлены как алиасы на `UNI.bat` (шапка `# 🤖 DEPRECATED by Hermes 2026-08-13: алиас`).
- Удалённые `uni/desktop/assets/avatar_*.svg` и `states/*.png` — удалены пользователем при реорганизации; в коммите отражено как delete (это намеренное действие пользователя, не моё).

## 4. BOUNDS / DPI (пруф позиции)

- DPI scale = 1.25 (экран 1920×1080 физ → 1536×864 лог).
- `workArea` = `{x:0,y:0,width:1536,height:816}` (без панели задач).
- Окно: `width:336, height:660` (логические DIP).
- **ДО фикса**: `final={"x":878,"y":0,...}` — окно ВВЕРХУ (баг).
- **ПОСЛЕ фикса**: `set-> 1188 143`, `final={"x":1188,"y":142,...}` — правый нижний, над треем. `816 - 662 - 12 = 142` ✓.
- Доказательство: `uni/desktop/desktop.log` строка `01:14:21`.

## 5. РЕЗУЛЬТАТЫ (что доказано)

| Проверка | Результат | Доказательство |
|---|---|---|
| Одно нажатие запускает стек | ✅ окно `visible=true`, серверы живы (1235/8787/8790 OPEN) | `desktop.log` `ready-to-show -> show`, netstat |
| Закрытие = убить всех | ✅ `/api/launcher/stop` → порты FREE, electron НЕТ, pids.json удалён | netstat + `ls pids.json` (нет) |
| Позиция над треем | ✅ `y:142` (правый нижний) | `desktop.log` |
| Повторный запуск без накопления | ✅ после чистки висячих — 1 инстанс | `tasklist electron` count |
| node --check (JS) | ✅ main.js, app.js, launcher.js OK | терминал |
| Пустой чат + чипы + лого в DOM | ✅ все id присутствуют | grep index.html |

## 6. ЧТО НЕ ДОКАЗАНО (блокер)

- **Визуальная приёмка** (аватар не обрезан, лого/чипы выглядят по референсу): vision-сервис недоступен (404 — внешний и локальный `browser_vision`). Проверка за пользователем. Скрин: `outbox/HERMES_UI_IDLE.png`.
- Этап C не завершён полностью: миссия из `/api/mission` (реальные этапы), наблюдение-глаз (лаймовый), финальный click-through, реальные микрофон/vision через backend — требуют отдельной итерации.

## 7. ВЫБРАННЫЙ ЛОГОТИП

- В шапке: `uni/webui/img/logo.png` (29 KB, PNG) — лучший из доступных (`uni.ico` 370 KB — это иконка окна/трея, не для шапки). Тот же `logo.png` используется как иконка окна/трея через `main.js` (иконка окна) — см. `createWindow` `icon`. Логотип в шапке: `<img class="brand-logo" src="../../webui/img/logo.png">`.

## 8. ПУТИ СКРИНОВ

- `outbox/HERMES_UI_IDLE.png` — idle-скрин (окно Юни, пустой чат). Источник: `agents/uni-codex/outbox/CAPTURE.png` (Electron capturePage).
- Остальные (DOGS_WORKING, DOGS_DONE, MISSION_*, CLASSIC_REGRESSION) — НЕ сделаны (Этап C не завершён).

## 9. ЗАПУСК ДЛЯ ДРУГИХ ИИ (как тестировать)

```
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -m uni        # альтернатива: двойной клик ЮНИ.lnk -> UNI.bat
```
- Админка статусов/логов: http://127.0.0.1:8787/admin-status.html
- Остановка стека: tray «Выход» (или `POST http://127.0.0.1:8790/api/launcher/stop`).

## 10. СТАТУС

НЕ «ГОТОВО» (по критерию директивы §16: обе приёмочные команды не введены через поле, миссия/собаки не проверены визуально, vision 404). Выполнено: запуск одним нажатием, чистый выход, позиция над треем, каркас интерфейса (лого/пустой чат/чипы/готово-пузырь). Этап C (миссия/наблюдение/микрофон/click-through) — следующая итерация.

Hermes = Гермес, агент-координатор Юни. Подпись: 2026-08-13.
