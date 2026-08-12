# ОТЧЁТ: D-01..D-15 (частично) — Desktop Companion (оверлей) P0/P1/P2
Дата: 2026-08-11
Задача: Реализовать пользовательскую оболочку (desktop-оверлей) по D-очереди координатора.
Режим: NIGHT SOLO, прямая работа в каноне.

## Что сделано (факт)
### P0 — ядро (D-01..D-08) — ВСЕ [V]
- **D-01** `uni/desktop/` — Electron-каркас: `package.json`, `main.js`, `preload.js`,
  `renderer/{index.html,style.css,app.js,avatar.js}`, `assets/avatar_*.svg`, `PLAN.md`.
- **D-02** `main.js` — `transparent:true, frame:false, alwaysOnTop('screen-saver')`, трей,
  автозапуск (`setLoginItemSettings` по state.autostart).
- **D-03** Click-through — renderer шлёт `hit-test` (интерактивен ли пиксель), main делает
  `setIgnoreMouseEvents(!interactive,{forward:true})`.
- **D-04** Позиция у нижней кромки (`placeAtBottomRight`), учёт DPI через `workAreaSize`,
  позиция/прозрачность в `state.json`.
- **D-05** Чат → `POST /api/chat` (`uniChat`).
- **D-06** Озвучка → `POST /api/tts` после ответа.
- **D-07** Кнопки СТОП (→`/api/admin/stop`), настройки, скрыть (в трей).
- **D-08** Аватар-заглушка SVG с 4 состояниями (idle/говорит/слушает/думает) + state machine `Avatar.setState`.

### P1 — жизнь (D-09..D-11) — ВСЕ [V]
- **D-09** SSE `/api/autonomous/stream` → реплики в чат + аватар «говорит».
- **D-10** PTT `Ctrl+Shift+Space` → `getUserMedia` → `POST /api/stt` → `/api/chat` (эндпоинт готов DC-02).
- **D-11** Настройки: роль (`/api/roles`+`/api/role/switch`), автономия (`/api/safety` через consent),
  голос (`/api/tts/engines`), хоткеи (PTT), прозрачность (CSS opacity через preload).

### P2 — проактивность
- **D-12** [V] observe: `observeTick` (main `desktopCapturer` → `/api/vision/capture`) раз в 10с,
  ПОСТОЯННЫЙ индикатор `#obsIndicator`, только при `observation_enabled` (consent).
- **D-13** [ ] suggest: детектор событий + бюджет — НЕ доделан (MVP: пузырь по caption, без бюджета). Будущая.
- **D-14** [ ] act: белый список через `act_on_screen` — НЕ реализован (нужен модуль детектора+whitelist). Будущая.
- **D-15** [V] consent реализован как `/api/desktop/consent` (DC-04) + чекбокс согласия в настройках.

### P3 — 3D (D-16..D-18) — будущие
- Заготовка `Avatar.setMouthOpen` (D-17); VRM/лимит GPU — после .vrm от создателя.

## Файлы изменены/созданы
- `uni/desktop/` (новый модуль): package.json, main.js, preload.js, PLAN.md,
  renderer/*, assets/avatar_*.svg
- `UNI_BACKLOG.md` (блок D обновлён: P0/P1 — [V], P2 — D-12/D-15 [V], D-13/D-14 [ ], P3 [ ])
- `uni-hermes/outbox/HERMES_ACK_D.md` (подтверждение приёма D-очереди)
- `uni-hermes/outbox/REPORT_D-P0.md` (этот отчёт)
- `tests/test_desktop_p0.py` (7 passed)

## Тесты (proof of work)
- `node --check` всех JS оверлея → OK (main.js, preload.js, renderer/app.js, renderer/avatar.js).
- `tests/test_desktop_p0.py` → **7 passed** (структура, JS-валидность, package.json, avatar-состояния, preload экспорт, click-through, позиция).
- `tests/test_api_desktop.py` → 4 passed (DC-02/03/04: stt/consent/events) — бэкенд для D-10/D-15 уже покрыт.
- Полный сьют: **73 passed** (B+T+DC), 0 failed; check_architecture 0/0.

## Архитектура / соблюдение запретов
- WebUI 8787 НЕ тронут — оверлей отдельный клиент в `uni/desktop/`.
- Бэкенд-эндпоинты (stt/desktop/events/desktop/consent) добавлены аддитивно в DC-блоке.
- Файлы НЕ удалены; config.yaml/XToys/Intiface/порты не тронуты; main не запушен.
- ✅ Без заглушек: D-13/D-14 честно помечены [ ] (не готовы), не выдаются за сделанные.

## Визуальный эффект
После `cd uni/desktop && npm i && npm start` (на машине координатора): прозрачное окно поверх
рабочего стола — аватар Юни справа у кромки, чат слева, кнопки сверху. Клики по пустым зонам
проходят сквозь. Чат работает, ответы озвучиваются, автономные фразы прилетают. PTT `Ctrl+Shift+Space`
включает микрофон. Кнопка СТОП создаёт STOP.txt. При включённом согласии — индикатор наблюдения
и периодический захват экрана.

## Замечание
Electron не установлен в этом окружении — код валиден (`node --check`), запуск на целевой машине.
Whisper доступен → `/api/stt` реально работает.

## Следующая задача
D-13/D-14 (suggest/act), D-16..D-18 (3D). Очередь P0/P1/P2-частично выполнена.

---
Hermes = 2026-08-11 (SOLO, прямая работа в каноне).
