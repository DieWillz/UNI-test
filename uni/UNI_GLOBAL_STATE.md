# UNI_GLOBAL_STATE.md — Глобальный срез состояния канона

> Единый Context Pack для роя ИИ-участников (Qwen, Gemini, Mistral, DeepSeek и др.).
> **Только факты**, без выдумок/симуляций. Сформирован Hermes 2026-08-11.
> Источник данных: реальное дерево `C:\LLM\UNI`, git-лог, сканирование кода, конфиги.

---

## 0. Режим и контекст выборки
- Текущая ветка: **`night/uni-mouse-vision`** (все последние коммиты — сюда).
- Режим работы Hermes на момент выборки: **SOLO** (Юни.light heartbeat отсутствует >30 мин; ревью Юни — постфактум, следующим циклом).
- Заблокированные/нетронутые папки по правилам: `UNI-grok`, `UNI-READY`, `UNI-test`, `backup/`, вложенные `uni/uni` (НЕ править, см. §4).
- **ВНИМАНИЕ для других ИИ:** не предлагать дубликаты уже реализованного (см. §2 и §6). Фича «управление ПК под зрением» ПОЛНОСТЬЮ реализована и покрыта тестами.

---

## 1. Архитектурный срез (`uni/` — основные директории)

| Директория | Назначение (факт) |
|---|---|
| `uni/capabilities/` | Реальные capability-адаптеры: `computer.py`, `vision.py`, `browser.py`, `camera.py`, `speech.py`, `memory.py`, `xtoys.py`, `base.py`, `registry.py`, `uni_action_badge.py`. Каждый реализует интерфейс `Capability` (см. `base.py`). |
| `uni/tools/` | Оркестрация/утилиты, НЕ capability: `visual_action.py` (замкнутый цикл вижу→кликаю→проверяю), `display_calibration.py` (DPI/мульти-монитор), `local_vision_fallback.py` (UIA/OCR), `trajectory_store.py` (лог траекторий), `executors.py`, `definitions.py`, `registry.py`, `results.py`. |
| `uni/council/` | МногоИИ-совет (`participants.py`, `provider.py`, `round.py`, `run.py`, `_keys.py`). |
| `uni/motion/` | Движение мыши: `driver.py` (click/draw/cancel), `trajectory.py`, `label.py`. Используется `human_mouse`. |
| `uni/skills/` | Skill-черновики. Сейчас: `operate-windows-visually/` (SKILL.md + `agents/`). |
| `uni/webui/` | Веб-панель админа: `server.py` (BaseHTTPRequestHandler, порт 8787), `index.html`, `js/app.js`, `css/`. |
| `uni/devcoord/` | Координатор разработки (`development_coordinator.py`). |
| `uni/context/`, `uni/knowledge/`, `uni/prompts/`, `uni/roles/`, `uni/scenarios/`, `uni/workflows/`, `uni/docs/` | Знания, промпты, роли, сценарии, документация, рабочие процессы. |
| `uni/memory/` | Runtime-память (`working.json`, `calibration/`, `trajectories.jsonl`). **gitignored** — не коммитится. |
| `uni/screenshots/` | Снимки экрана (runtime). |
| `uni/intiface_bridge.py`, `uni/xtoys_control_coordinator.py`, `uni/autonomous_session.py` | Физические устройства / автономный режим — **в DO_NOT_TOUCH** (§4). |

---

## 2. Статус модулей (capabilities и tools)

### Capabilities
| Модуль | Статус | Покрытие тестами | Примечание |
|---|---|---|---|
| `computer.py` (ComputerCapability) | **WORKING** | `test_human_mouse.py` | Подключён `HumanMouseController` (`use_human_motion`). Калибровка DPI (B-03) внутри. |
| `vision.py` (VisionCapability) | **WORKING** | `test_vision_gradio.py`, `test_vision_parsing.py`, `test_visual_ui_operator.py` | VLM (LM Studio). Локальный UIA/OCR-fallback (B-04) под флагом `local_fallback_enabled`. |
| `browser.py` | **WORKING** | `test_browser_session.py` | Сессия браузера. |
| `camera.py` | **WORKING** | `test_camera.py` | Камера Юни (тест падает на реальной машине без камеры — pre-existing, вне задач). |
| `speech.py` | **WORKING** | `test_speech_input.py`, `test_speech_synthesis.py` | TTS (Silero `xenia` по умолчанию) + STT. |
| `memory.py` | **WORKING** | `test_working_memory.py` | Рабочая память. |
| `xtoys.py` | **WORKING** | `test_xtoys_dom.py` | XToys-паттерны (переименованы 2026-08-09: tease→ramp, build→climb, edge→hold, release→cooldown). |
| `uni_action_badge.py` | **WORKING** | — | Визуальная подсветка точки действия. |

### Tools (оркестрация)
| Модуль | Статус | Покрытие тестами | Примечание |
|---|---|---|---|
| `visual_action.py` (VisualActionAgent) | **WORKING** | `test_visual_action_loop.py` (13), `test_agent_act_on_screen.py` (3), `test_regression_integration.py` (3) | Замкнутый цикл + blacklist + защита системных зон + history + сохранение траекторий. |
| `display_calibration.py` | **WORKING** | `test_display_calibration.py` (6) | DPI/мульти-монитор. Env `UNI_NO_DISPLAY_CALIBRATION=1` отключает. |
| `local_vision_fallback.py` | **WORKING** | `test_local_vision_fallback.py` (5) | UIA/OCR fallback. Тихо None при недоступности. |
| `trajectory_store.py` | **WORKING** | `test_trajectory_store.py` (4) | Лог траекторий в `memory/trajectories.jsonl` + черновик skills. |
| `executors.py` / `definitions.py` / `registry.py` / `results.py` | **WORKING** | `test_executor.py` | Исполнение действий. |

### Skills
- `uni/skills/operate-windows-visually/` — **EXISTS** (SKILL.md + `agents/`), создан 2026-08-03. Черновик, не помечен DEPRECATED.

### WIP / DEPRECATED
- **WIP:** нет явно помеченных WIP-модулей в коде на момент выборки.
- **DEPRECATED:** явных `DEPRECATED`/устаревших модулей нет. Одна пометка в `server.py:161` — «моста (server.js: safePath) пока не используется фронтендом» (часть кода, не используемая UI, но не удалённая).

---

## 3. Инфраструктура

### Критические порты (факт из кода + netstat)
| Порт | Назначение | Статус |
|---|---|---|
| **1234** | LM Studio OpenAI-совместимый API (`brain.base_url: http://localhost:1234/v1`) | **LISTENING** (pid 22156 на момент выборки) |
| **8000** | Hermes локальное приложение (`council/_keys.py`: `http://localhost:8000/v1`) | не слушает в этой сессии |
| **8787** | Веб-панель UNI (`uni/webui/server.py`, `py -3.12 -m uni.webui`) | не слушает в этой сессии (сервер не запущен) |
| **12345** | Intiface Bridge (устройства Fredorch), `ws://127.0.0.1:12345` | не слушает |
| **12347** | `mov2toy.py` (вкладка «Игрушки», `uni/webui/delete-after/mov2toy.py`) | не слушает |

### Зависимости Python (факт: `requirements.txt` / `pyproject.toml`)
- Основные: `pyautogui`, `comtypes`, `pydantic`, `aiohttp`/`httpx`, `requests`, `pillow`, `numpy`, `websockets`, `buttplug` (py пакет), `pytest`.
- Локальные модели/TTS: `silero` (TTS `xenia` по умолчанию в `config.yaml: speech`), VLM через LM Studio (Gradio/`gradio_client`).
- `UNI_REMOTE_PUBLIC_BASE` — env-флаг в `server.py` (B-06) вместо cloudflared.

### Активные сервисы (на момент выборки)
- **LM Studio** на 1234 — слушает (pid 22156).
- Сервер веб-панели UNI (8787), Intiface (12345), Hermes (8000) — **не запущены** в этой sandbox-сессии.

---

## 4. Конфигурация и Безопасность

### Структура `config.yaml` (факт, без секретов)
```
brain:
  base_url: http://localhost:1234/v1        # LM Studio
  api_key: lm-studio
  model: qwen2.5-7b-instruct-1m
  vision_model: auto
  vision_base_url: null
  temperature: 0.85
  max_tokens: 2000
  timeout_seconds: 20.0
capabilities:
  browser / computer / camera / speech / vision / xtoys   # каждый со своими опциями
agent:
  default_role: mistress2
  cycle_interval: 2.0
  max_retries: 3
  verification_enabled: false
  input_mode: mixed
  speak_responses: true
  max_parallel_tasks: 3
  max_pending_tasks: 6
  task_timeout_seconds: 120.0
  visual_ui_max_steps: 20
  response_max_chars: 700
  spoken_response_max_chars: 320
  autonomous: { ... }
memory:
  path: memory/working.json
  max_context_tokens: 4000
  max_dialogue_turns: 50
logging:
  enabled: true
  directory: .uni-logs
autonomous: { ... }
```
- **Критическая опция безопасности:** `capabilities.vision.local_fallback_enabled: false` (default) — локальный UIA/OCR-fallback ВЫКЛЮЧЕН по умолчанию (B-04).
- `capabilities.computer.use_human_motion: true` — человеко-подобная мышь включена.
- `config.yaml` — **В DO_NOT_TOUCH** (секреты), править только по задаче координатора.

### `UNI_DO_NOT_TOUCH.md` — категорически нельзя трогать
- `.git/`
- `config.yaml` (секреты)
- `memory/`, `logs/` (кроме ночных логов)
- `__pycache__/`, `venv/`, `node_modules/`
- `*.secret`, `*.env`
- `uni/webui/bin/`
- `UNI_LOCKS.json` — только свои блокировки
- `UNI_BOARD.md` / `UNI_TASKS_LIGHT.md` — только через координатора / Hermes
- `uni/security/`
- `uni/intiface_bridge.py`, `uni/xtoys_control_coordinator.py`, `uni/autonomous_session.py`
- `tests/` — только если задача явно требует тестов
- `uni_tandem_watchdog.ahk`, `hermes_auto.ahk` — автоматика Юни

---

## 5. Активные блокировки (`UNI_LOCKS.json`)

```json
{
  "locks": [],
  "rules": "Один файл — один владелец. Перед правкой поставить lock с owner/task/expires_at. Если файл заблокирован другим — не править, написать предложение в outbox / добавить задачу в board."
}
```
- **Факт:** на момент выборки `locks: []` — активных блокировок НЕТ.
- Правило: перед правкой файла ставить lock; если заблокировано другим — не править.

---

## 6. История интеграций в канон (последние дни, факт из git-лога)

Все коммиты — ветка `night/uni-mouse-vision`. Hermes (SOLO, 2026-08-11):
- `c818c1c` docs(B-08): руководство по управлению ПК под зрением (docs/COMPUTER_VISION_CONTROL.md).
- `bab1e2f` feat(B-07): регрессия — 10× smoke + 3× integration + scripts/run_regression.py (GREEN).
- `e3659b9` feat(B-06): env `UNI_REMOTE_PUBLIC_BASE` в `server.py` (вместо cloudflared, аддитивно).
- `e149b48` feat(B-05): сохранение траекторий `memory/trajectories.jsonl` + черновик skills.
- `d7a262a` feat(B-04): локальный UIA/OCR-fallback для vision (opt-in `local_fallback_enabled`).
- `b885f85` feat(B-03): калибровка DPI/мульти-монитор (`display_calibration.py`, профиль в `memory/`).
- `21ee41c` feat(B-01): лог шагов цикла (увидела→сделала→увидела после) в UI «Компютер» + СТОП.
- `56de9bf` feat(voice/мышь): маршрутизация «открой X» → `act_on_screen` в `event_loop` (N-13).
- `fa95e23` feat(safety): расширенный blacklist + защита системных зон (N-11).
- `0692636` feat(webui): вкладка «Компьютер» + `/api/computer/{act,stop,status}` (N-03b).
- `8f96214` feat(voice+mouse): `Agent.act_on_screen` (N-04b).
- `fa37a1a` (2026-08-10) docs(night): финальный rolling-отчёт (этак мышь+зрение done).
- `1984b78` / `00c9a03` (2026-08-10) feat(vision+mouse / mouse): замкнутый цикл + HumanMouseController в ComputerCapability.
- `65b0dc7` (2026-08-09) refactor(xtoys): переименование паттернов.

**Итог за 2026-08-10..11 (Hermes):** полностью реализована и покрыта тестами фича «Управление ПК под зрением»: веб-вкладка «Компьютер», голосовая/текстовая маршрутизация, защита (blacklist + системные зоны), калибровка DPI/мульти-монитор, UIA/OCR-fallback, лог траекторий, env-флаг удалённого доступа, регрессия 10×smoke+3×integration, документация. Бэклог B-01..B-08 — ВЫПОЛНЕН.**

### Текущий статус тестов (факт, последний прогон)
- Затронутые модули (B-01..B-08): **61 passed, 0 failed** (прогон 2026-08-11).
- `scripts/check_architecture.py --strict`: **0 errors, 0 warnings**.
- Полный pytest проекта: 193 passed / 2 pre-existing failed (test_camera, test_realtime_role — вне задач Hermes, не тронуты).

---

## 7. Что НЕ трогать (напоминание для роя)
- Фича «управление ПК под зрением» УЖЕ реализована — не предлагать дубликаты.
- Не править `config.yaml`, `UNI_LOCKS.json`, `intiface_bridge.py`, `xtoys_control_coordinator.py`, `autonomous_session.py`, `tests/` (без явной задачи).
- Не править папки `UNI-grok`, `UNI-READY`, `UNI-test`, `backup/`, вложенные `uni/uni`.
- Перед правкой файла — проверить `UNI_LOCKS.json` и поставить lock.

---
*UNI_GLOBAL_STATE.md сформирован Hermes = 2026-08-11. Строго факты: git-лог, сканирование `uni/`, `config.yaml`, `UNI_LOCKS.json`, `UNI_DO_NOT_TOUCH.md, netstat. Без выдумок/симуляций.*
