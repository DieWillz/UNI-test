# PLAN: UNI Desktop Companion — реализация (Hermes SOLO, 2026-08-11)

Собственный план по дополнительной директиве координатора. Базируется на файле
«Основная оболочка Юни.md» (концепт) + уже сделанном блоке DC-01..DC-09 и существующем
каноне (`server.py` на 8787, `uni/capabilities/*`).

## 0. Текущий статус (факт из кода)
- **Уже есть (канон):** `/api/chat`, `/api/tts`, `/api/tts/engines`, `/api/roles`,
  `/api/role/switch`, `/api/safety`, `/api/autonomous/stream` (SSE), `/api/autonomous/audio/<file>`,
  `/api/camera/start`, `/api/vision/capture`, `POST /api/admin/stop` (→ STOP.txt).
- **Сделано в DC-01..DC-09 (этот сеанс):**
  - `uni/capabilities/stt.py` + `POST /api/stt` (опциональный Whisper; faster-whisper доступен).
  - `GET /api/desktop/events` (SSE для оверлея).
  - `GET/POST /api/desktop/consent` + журнал `uni/memory/consent_log.jsonl`.
  - Черновик Electron-клиента в `uni/webui/desktop/` (main.js, index.html, style.css, app.js).
- **Расхождение со спекой D:** D-10 («/api/stt НЕТ») и D-15 («/api/consent НЕТ») уже выполнены
  как DC-02/DC-04. В плане D-задачи помечаются как «готово/переиспользуется».

## 1. Архитектура
```
uni/desktop/                        ← КАНОНИЧНАЯ папка оверлея (новая, отдельная от webui/)
├── package.json                    Electron + зависимости
├── main.js                        main process: прозрачное окно, alwaysOnTop, трей, PTT, SSE-клиент
├── preload.js                     безопасный мост IPC (contextIsolation)
├── PLAN.md                        этот файл
├── renderer/
│   ├── index.html                 компоновка (чат слева, аватар справа, кнопки сверху)
│   ├── style.css                  прозрачность, позиция у кромки, DPI-масштаб
│   ├── app.js                     чат→/api/chat, TTS, SSE autonomous/stream, desktop/events,
│   │                              PTT→/api/stt, кнопки, настройки, avatar state machine
│   └── avatar.js                  состояния idle/говорит/слушает/думает + (P3) VRM/lip-sync
├── assets/                        avatar_idle.png, avatar_talk.png, ... (заглушки, рисует создатель)
└── tests/                         (интеграционные проверки собираются в tests/test_desktop_*.py)
```
Сервер 8787 НЕ трогаем. Оверлей — отдельный клиент, ходит по HTTP/SSE к тем же эндпоинтам.

## 2. Порядок (P0 → P3) и что делается

### P0 — ядро (D-01..D-08)
- D-01: перенести/дополнить каркас из `uni/webui/desktop/` → `uni/desktop/` (preload.js добавить).
- D-02: `main.js` — `transparent, frame:false, alwaysOnTop('screen-saver'), skipTaskbar,
  Tray, автозапуск через app.setLoginItemSettings`.
- D-03: click-through — renderer шлёт `hit-test` (интерактивен ли пиксель), main делает
  `setIgnoreMouseEvents(!interactive, {forward:true})`.
- D-04: позиция `y = screen.height - height - taskbar`; учёт `webFrame.setZoomFactor` по DPI;
  хранить позицию в `uni/desktop/state.json`.
- D-05: чат-панель → `POST /api/chat` (поле message).
- D-06: после ответа → `POST /api/tts` (возвращает audio_url) → `<audio>` / Web Audio.
- D-07: кнопки СТОП (→`/api/admin/stop`), настройки (toggle panel), скрыть (minimize to tray).
- D-08: аватар-заглушка PNG + state machine (4 состояния); assets рисует создатель (я кладу
  плейсхолдер-SVG, чтобы окно не падало).

### P1 — жизнь (D-09..D-11)
- D-09: SSE `/api/autonomous/stream` → реплики в чат + аватар переходит в «говорит».
- D-10: PTT `Ctrl+Shift+Space` → `getUserMedia` → `POST /api/stt` → `/api/chat` (эндпоинт есть).
- D-11: панель настроек — роль (`/api/roles`+`/api/role/switch`), автономия (`/api/safety`),
  голос (`/api/tts/engines`), хоткеи, прозрачность (CSS opacity).

### P2 — проактивность (D-12..D-15)
- D-12: observe — `setInterval` захват экрана (через `/api/vision/capture` или локальный
  screenshot) раз в 5–15с; ПОСТОЯННЫЙ индикатор «👁 наблюдает»; только если
  `/api/desktop/consent` → observation_enabled=true.
- D-13: suggest — эвристический детектор событий (ошибка в окне/диалог/простой) → пузырь/голос;
  бюджет N/час + «не беспокоить» (тихие часы) в `state.json`.
- D-14: act — белый список действий через `act_on_screen`; всё прочее → consent-подтверждение.
- D-15: consent-диалоги L2/L3 в оверлее → `POST /api/desktop/consent` (уже есть).

### P3 — 3D (D-16..D-18)
- D-16: three-vrm рендер `.vrm` (VRoid Studio экспорт от создателя) вместо PNG.
- D-17: lip-sync — `AnalyserNode` на TTS-аудио → морфинг рта (или blend-shape).
- D-18: лимит 30 fps, `powerPreference:'low-power'`, настройка «качество аватара».

## 3. Риски и как снижаем
| Риск | Снижение |
|---|---|
| Прозрачность/click-through на Windows 10 | проверить на целевой машине; `ready-to-show` перед show; hit-test по альфе |
| GPU-конфликт с LM Studio (3060 12GB) | D-18: 30fps, low-power, fbx low-poly |
| Хоткеи конфликтуют с AHK (`Ctrl+Alt+*`, kill-switch `Ctrl+Alt+Shift+U`) | PTT = `Ctrl+Shift+Space` (свободен), вынесен в настройки |
| Приватность скриншотов | только локально, индикатор, срок хранения в `state.json` |
| Не сломать WebUI 8787 | оверлей — отдельный клиент; канон только аддитивно |
| Создатель рисует аватара | кладу SVG-плейсхолдер, чтобы окно не падало без ассетов |

## 4. Proof of work на задачу
- Каждый D-шаг: изменение в `uni/desktop/` + (если задействован бэкенд) тест в `tests/`.
- Electron-код валидируется `node --check`.
- Отчёт `uni-hermes/outbox/REPORT_D-XX.md` после каждой задачи.
- Heartbeat `uni-hermes/logs/hrm_heartbeat.txt` каждые 10–15 мин.
- Зеркалирование `UNI-mcp-server/uni-local/uni/desktop/`.

## 5. Что уже готово из D (переиспользуется, не делаю заново)
- D-10 `/api/stt` → готово (DC-02).
- D-15 `/api/consent` → готово как `/api/desktop/consent` (DC-04).
- Бэкенд-эндпоинты чата/tts/roles/safety/autonomous/stream → уже есть в каноне.

---
Hermes = 2026-08-11 (SOLO). План — proof of work для блока D.
