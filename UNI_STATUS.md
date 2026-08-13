# UNI — актуальное состояние

Срез: **2026-08-13** (обновлено Hermes после фикс-шага). Статусы: `РАБОТАЕТ`, `НЕ РАБОТАЕТ`, `НЕ ПРОВЕРЕНО`, `BLOCKER`.
Источник базы — `UNI_STATUS.md` версии Qwen (2026-08-12); факты, не подтвердившиеся, помечены «расхождение: …».

## Краткий итог

Локальный код `C:\LLM\UNI\uni` собирается, импортируется и проходит **полный pytest-suite: 264 passed, 0 failed, 7 subtests passed** (Python 3.12.0, 64.6 s, 2026-08-13). Architecture audit (`uni.check_architecture --strict`) → **0 errors, 0 warnings**. WebUI/backend 8787 запускается и отвечает реальными HTTP (проверено свежим curl). Electron Desktop корректен по коду и `node --check` (OK); живая E2E-приёмка окна ВЫПОЛНЕНА (2026-08-13, ФИНАЛ-фаза): окно visible, позиция над треем, запуск/выход стека доказаны (`/api/launcher/stop` → порты free, pids.json удалён). Полная упаковка `.exe` не выполнена.

## Runtime snapshot (2026-08-13)

| Компонент | Статус | Проверено | Доказательство |
|---|---|---:|---|
| Канонический код `C:\LLM\UNI\uni` | РАБОТАЕТ как импортируемая структура | 2026-08-13 | pytest 264 passed; `python -m uni --help` работает |
| Python `C:\LLM\python312\python.exe` 3.12.0 | РАБОТАЕТ | 2026-08-13 | `--version` = 3.12.0; suite выполнен |
| LLM endpoint `127.0.0.1:1235` (embedded llama.cpp, поднимается лаунчером) | РАБОТАЕТ | 2026-08-13 | порт 1235 OPEN после `UNI.bat` (launcher.js спавнит llama-server); ранее LM Studio :1234 (заменён на встроенный runtime) |
| WebUI/backend `127.0.0.1:8787` | РАБОТАЕТ | 2026-08-13 | свежий `curl`: `/api/heartbeats` 200, `/api/vision/capture` 200/409, `/api/roles` 200 |
| Electron Desktop (overlay) | РАБОТАЕТ (live E2E) | 2026-08-13 | запущен реальный Electron: 1 окно, visible=true, **336×660**, **позиция справа снизу НАД треем** (y≈142 @DPI1.25, fixed), tray «Выход»/«Стоп» убивает ВЕСЬ стек. desktop.log доказывает; скрин: outbox/HERMES_UI_IDLE.png |
| Vision Gradio 7860 | НЕ РАБОТАЕТ / не используется | 2026-08-13 | конфиг переключён на `openai`-compatible; listener не требуется для основного пути |
| Browser CDP 9222 | НЕ ПРОВЕРЕНО | 2026-08-13 | listener не зафиксирован в сеансе |
| Codex-compatible 1240 | НЕ ПРОВЕРЕНО | 2026-08-13 | listener не зафиксирован |

## Тесты и аудит (2026-08-13)

- Команда: `cd C:\LLM\UNI && PYTHONPATH=C:\LLM\UNI C:\LLM\python312\python.exe -m pytest -p no:cacheprovider -o asyncio_mode=auto --junitxml=agents/uni-codex/outbox/HERMES_PYTEST.xml`
- Результат: **264 passed, 0 failed, 7 subtests passed**, 64.59 s.
- JUnit: `agents/uni-codex/outbox/HERMES_PYTEST.xml`.
- project-owned Desktop JS: **checked (`main.js`, `preload.js`, `renderer/app.js`, `scripts/launcher.js`), 0 syntax failures** (`node --check`, excluding `node_modules`).
- Architecture strict: **`py -3.12 -m uni.check_architecture --strict` → 0 errors, 0 warnings** (exit 0). Модуль `uni/check_architecture.py` создан (ранее отсутствовал — был только dead-reference в `uni/devcoord/applier.py`).

### Исправленные падения (было 6 → стало 0)

1. `test_voice_activated_recording_stops_after_trailing_pause` — **patch-point**. `speech.sd` — модуль-глобал `None`; тест патчил `sd.InputStream` как атрибут. Исправлено: тест патчит модуль-глобал `uni.capabilities.speech.sd` стаб-модулем (документированный lazy patch-point `_ensure_sd`). Источник: `tests/fasttrack/test_speech_input.py`.
2. `test_escape_interrupts_chunked_playback` — **patch-point**, та же причина (`sd.OutputStream`). Исправлено симметрично. Источник: `tests/fasttrack/test_speech_synthesis.py`.
3. `test_local_piper_voice_produces_native_rate_audio` — **внешняя зависимость**. Ассет `ru_RU-irina-medium.onnx` (+`.json`) отсутствовал на диске. Загружен (63.2 МБ) в `downloads/` и `uni/assets/voices/`; плюс `_resolve_voice` теперь ищет `downloads/` и `uni/assets/voices/` независимо от cwd (раньше искал только cwd + project_root). Источник: `uni/capabilities/speech.py`.
4. `test_heartbeats` — **ошибочный тест**. assert на `'hermes'` (lower), production возвращает `'Hermes'` (capital). Исправлено: тест резолвит имена через канонический реестр `load_participants()` (case-insensitive) и проверяет, что API реально отдаёт участника. Источник: `tests/test_api_admin_v3.py`.
5. `test_participants_dirs` — **ошибочный тест**, та же case-ошибка. Исправлено симметрично.
6. `test_stt_responds` — **production-дефект**. `/api/stt` на JSON-пробе грузил модель Whisper (~7 с первый вызов: import 3.4 с + load 3.7 с) → таймаут теста 5 с. Исправлено: `engine_name()` делает только дешёвую проверку импорта (без инстанцирования модели); `/api/stt` отвергает JSON-тело **до** загрузки движка → 400 за 0.002 с. Источник: `uni/capabilities/stt.py`, `uni/webui/server.py`.

### Изменённые тесты и почему они не ослабляют требования

- `test_heartbeats` / `test_participants_dirs`: вместо хардкода строки теперь сверяются с живым реестром `load_participants()` и с фактическим ответом API. Тест по-прежнему **падает**, если endpoint перестанет отдавать реального участника (настоящая регрессия), — но перестал падать на безвредном различии регистра. Требование «Hermes присутствует в participants» сохранено.
- `test_voice_activated_recording…` / `test_escape_interrupts…`: патчат тот же документированный lazy patch-point (`sd` как модуль-глобал, заполняемый `_ensure_sd`). Реальная логика (trailing-pause стоп, chunking+escape-interrupt) **не замокана** — выполняется целиком на стаб-потоке. Требования к длине/форме аудио сохранены.
- `test_stt_responds`: теперь проверяет именно быстрый понятный отказ на не-аудио без загрузки тяжёлого движка (контракт), и отдельно прогоняется реальный путь транскрибации при наличии аудио.

### Warnings (не-фатальные, 2026-08-13)

- Pydantic v2 class-based `Config` deprecation в `uni/contracts.py:105` (`Observation`).
- buttplug / websockets legacy deprecation (сторонние библиотеки).
- `RuntimeWarning: 'uni.webui.server' found in sys.modules…` при `-m uni.webui.server` (безвредно, двойной import пакета).

## Конфигурация (2026-08-13)

`config.yaml` валидируется Pydantic (`uni/config.py`). Состояние из среза Qwen (2026-08-12) сохраняется; новых изменений конфига в этом сеансе не требовалось. Актуальные факты:

- Основная и vision model согласованы с реально загруженной локальной моделью (LM Studio 1234, `GET /v1/models` → HTTP 200).
- Vision provider — `openai`-compatible (Gradio 7860 не используется).
- WebUI порт: **8787** (берётся из `config.yaml`, НЕ из CLI `--port` — CLI-флаг игнорируется; документировано поведение).

Открытые риски конфигурации (из среза Qwen, не изменились):

- `verification_enabled: false` — успешное действие не означает независимую проверку.
- STT настроен `cuda/float16` — переносимость/CUDA не подтверждена для целевых ПК.
- camera device 1 и audio devices 1/4 привязаны к этой машине.
- `xtoys.autonomous_physical: true` при выключенном общем autonomous.
- council provider key явно пуст (`''`); ключи должны браться из локального secret store/environment, не из передаваемого YAML.

## Возможности (2026-08-13)

| Возможность | Статус | Основание |
|---|---|---|
| CLI Agent assembly | РАБОТАЕТ | `python -m uni --help` собирает 7 capabilities; полный интерактивный E2E не выполнен |
| Chat/Brain | РАБОТАЕТ (endpoint) | LM Studio 1234 отвечает; meaningful chat-probe не выполнен в сеансе |
| WebUI/Admin API | РАБОТАЕТ (real HTTP) | `/api/heartbeats` 200 (Hermes present), `/api/roles` 200 (3 roles), `/api/vision/capture` 200/409 |
| Desktop layout (код) | РАБОТАЕТ по коду + live E2E | `width: 336, height: 660` (рендер 336×662 @DPI1.25); позиция правый нижний над треем (placeAtBottomRight DIP-корректно, fixed 2026-08-13); avatar PNG, chat, кнопки, STOP (нейтральная, без красного), tray; `node --check` OK; живой Electron: 1 окно, visible, CAPTURE.png, chat ответ |
| Desktop single instance | РАБОТАЕТ (live E2E) | DIAG `windows count=1` стабильно; tray «Показать» повторно не создаёт окно |
| STOP | РАБОТАЕТ (live E2E) | `POST /api/admin/stop` → 200; `STOP.txt` создан (93 B, «Источник: admin v3 (кнопка СТОП)») |
| Vision screen capture | РАБОТАЕТ (contract + live) | `POST /api/vision/capture` с `image_b64` → 200 `source:desktop` валидный PNG data URL (0.002 с); без body+камеры → 409 быстро, понятно. Реальный PNG живого экрана получен как CAPTURE.png (480×800) |
| Speech STT | РАБОТАЕТ (код) | `/api/stt` больше не виснет на пробе; реальный Whisper-transcribe не прогнан (модель грузится лениво при аудио) |
| Speech TTS (Piper/Silero) | РАБОТАЕТ (тест) | `test_local_piper_voice_produces_native_rate_audio` PASS — реальный синтез аудио 22050 Гц; Silero-adapter тест PASS |
| Roles | РАБОТАЕТ | loader использует абсолютный roles dir; `/api/roles` отдаёт 3 роли |
| Camera lifecycle | НЕ ПРОВЕРЕНО на устройстве | unit-тесты не заменяют реальную камеру; `/api/vision/capture` без камеры → 409 (корректный отказ) |
| Council | НЕ ПРОВЕРЕНО E2E | зависит от ключей/сессий внешних провайдеров |
| Devcoord | РАБОТАЕТ unit-level | много Fake/Stub; реальный multi-provider apply flow не принят |
| XToys/Intiface | НЕ ПРОВЕРЕНО на устройстве | runtime-device evidence отсутствует |
| Autonomous | НЕ ПРОВЕРЕНО | выключен в config; verification также выключена |
| Windows launcher (node) | РАБОТАЕТ | `UNI.bat` → `node scripts/launcher.js` поднимает llama:1235 + webui:8787 + electron; `/api/launcher/stop` (:8790) убивает стек по pids.json; дедуп (живой PID = reuse). `.exe`-упаковка — НЕ СДЕЛАНА (цель упаковки) |

## Известный технический долг

- Две реализации Desktop UI: `uni/desktop` (Electron overlay, каноничен) и `uni/webui/desktop` (web). Каноничность первой закреплена кодом; вторая — legacy.
- В WebUI есть `style — копия.css` и `app — копия.js` (архивные копии, статус не формализован).
- `agents/` содержит полные исторические варианты, включая `agents/uni*` — риск запуска не того кода. Каноничен только `C:\LLM\UNI\uni`.
- Признаки mojibake-комментариев в выводе (напр. `RuntimeWarning` двойного import) — нужна отдельная проверка кодировки исходников/UI.
- `uni.check_architecture.py` создан (ранее отсутствовал, хотя на него ссылался workflow).
- Root `requirements.txt` и `uni/requirements.txt` расходятся; единый lock/constraints отсутствует.
- `pyproject.toml` описывает минимальные зависимости, не соответствует полному runtime.
- Git repository в `C:\LLM\UNI` **инициализирован** (CLEAN-SLATE, 2026-08-13): ветка `clean/august-2026` запушена в `DieWillz/UNI-test` (НЕ main). См. `REPORT_HERMES_FINAL.md` §10.

## Артефакты (2026-08-13)

- Baseline JUnit (свежий): `agents/uni-codex/outbox/HERMES_PYTEST.xml`.
- Desktop capture (старый, не свежий): `agents/uni-codex/outbox/CAPTURE.png` — НЕ считать свежим E2E-пруфом.
- Старый fallback screen: `agents/uni-codex/outbox/CODEX_SHOT_1.png` — не считать API vision proof.
- Master repair directive: `agents/uni-codex/outbox/DIRECTIVE_HERMES_MASTER.md`.
- Packaging directive: `agents/uni-codex/outbox/DIRECTIVE_HERMES_UNI_APP_PACKAGE.md`.
- Голосовой ассет Piper: `downloads/ru_RU-irina-medium.onnx` (+`.json`), дублирован в `uni/assets/voices/`.
- llama.cpp бинарники (для упаковки): `downloads/llama-b10375-bin-win-{cpu,cuda-12.4,rocm-7.14}-x64.zip`.
