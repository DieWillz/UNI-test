# UNI — канонический контекст проекта

Обновлено: 2026-08-13. Устойчивая картина проекта. Для текущего состояния — `UNI_STATUS.md`, для работы — `UNI_TASKS.md`.

## Назначение

UNI — локальный Windows AI-агент с текстовым и голосовым взаимодействием, управлением браузером/компьютером, зрением, камерой, памятью, ролями, автономным режимом и опциональным управлением XToys/Intiface. Интерфейсы: CLI, WebUI/admin и Electron Desktop Companion. Человек-координатор управляет роем ролей ИИ.

## Канонические каталоги (2026-08-13, сверено с диском)

- `C:\LLM\UNI\uni` — **единственный** канонический production-код.
- `C:\LLM\UNI\tests` — канонические тесты.
- `C:\LLM\UNI\config.yaml` — локальная runtime-конфигурация (валидируется Pydantic).
- `C:\LLM\UNI\downloads` — тяжёлые ассеты упаковки и модели (llama.cpp бинарники, Piper-голос). **Канонично для внешних ассетов** (ранее предлагалось `uni/assets/voices`, теперь `_resolve_voice` ищет оба места).
- `C:\LLM\UNI\uni\assets\voices` — копия Piper-голоса внутри канона (для self-contained работы без `downloads`).
- `C:\LLM\UNI\agents\uni-codex\outbox` — **каталог обмена с Codex** (актуальный путь; прежнее имя `UNI-mcp-server` заменено). Сюда класть `HERMES_PYTEST.xml`, `REPORT_HERMES_FINAL.md`, `CAPTURE.png`, `CODEX_SHOT_1.png`.
- `C:\LLM\UNI\agents\artifacts` — большие логи и screenshots (не в корень).
- `C:\LLM\UNI\agents\uni*` — исторические рабочие копии ИИ; **НЕ канонический код**, риск запуска не того модуля.

> Правило именования: зеркало/обмен → `agents\uni-codex\outbox`. Старая папка `UNI-mcp-server` более не актуальна (координатор переименовал).

## Архитектура

```text
User/UI
  ├─ CLI:            python -m uni  (PYTHONPATH=C:\LLM\UNI; py -3.12)
  ├─ WebUI/Admin:    python -m uni.webui  → 127.0.0.1:8787
  └─ Electron Desktop Companion (uni/desktop, start.bat)
           │
           ▼
        Agent / EventLoop
           ├─ Brain ──> OpenAI-compatible model server (LM Studio 1234)
           ├─ ToolExecutor ──> CapabilityRegistry ──> Capabilities
           ├─ Memory / Roles / Safety state
           └─ Autonomous / VisualAction loops
```

1. `uni.config` загружает YAML в Pydantic-модели.
2. `uni.agent.Agent` собирает Brain, BrowserSession, WorkingMemory, capabilities, ToolExecutor, EventLoop, AutonomousController.
3. Capabilities: `speech`, `computer`, `camera`, `browser`, `vision`, `memory`, `xtoys`.
4. `uni.brain.Brain` использует OpenAI-compatible LLM endpoint (LM Studio `127.0.0.1:1234`, `GET /v1/models` → 200).
5. `uni.webui.server` — локальный HTTP WebUI/admin API, **порт 8787** (из `config.yaml`; CLI `--port` игнорируется).
6. `uni.desktop` — Electron overlay: preload bridge, чат, VRM/SVG avatar, tray «Показать», desktop-события. Layout **383×640**.
7. `uni.council` — параллельные внешние/локальные советники (недоверенные данные).
8. `uni.devcoord` — координация разработчиков/провайдеров, верификация и применение.
9. `uni.check_architecture` — AST-аудит (ADR-0005), `py -3.12 -m uni.check_architecture --strict` → 0/0.

## Основные entrypoints (2026-08-13)

- `cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m uni` — интерактивный агент.
- `… -m uni --text` — текстовый режим.
- `… -m uni --autonomous` — автономный (при разрешённой конфигурации).
- `… -m uni.webui` — WebUI/admin на 8787.
- `uni\desktop\start.bat` — Electron Companion.

## Контракты

- Каноническое действие: `Action(name="capability.action", params, id)`.
- Канонический результат: `ActionResult` (`success`, `error`, `verified`, retry, timestamp).
- Observation — bounded snapshot, не вечный факт.
- Реальная готовность требует `ACTION → RESULT → OBSERVATION`.
- WebUI: chat, roles, TTS/STT, camera/vision, desktop consent/events, computer actions, autonomous, council, XToys/Intiface, admin.
- **Vision capture contract (`/api/vision/capture`)**: Desktop шлёт скриншот как `image_b64` в теле → 200 `{image_b64: "data:image/png;base64,…", source:"desktop"}` (валидация base64, без hang, без камеры). Без тела и при недоступной камере → 409 с понятным сообщением. Камера — только явный opt-in fallback.

## Конфигурация и секреты

- Pydantic-схема в `uni/config.py`; неизвестные YAML-поля могут молча игнорироваться — конфиг валидировать через `Config`.
- API-ключи НЕ хранятся в передаваемых документах/сборках/диагностических ZIP.
- Перед публичной упаковкой секреты выносятся в локальный secret store/environment и перевыпускаются.
- Dev LLM — локальный OpenAI-compatible endpoint. Публичный пакет обязан иметь CPU fallback и не зависеть от LM Studio.

## Правила для всех ИИ

1. Сначала читать `UNI_CONTEXT.md`, `UNI_STATUS.md`, затем строку `UNI_TASKS.md`.
2. Не редактировать `agents\uni*` как production-код.
3. Перед работой назначить задачу; после — обновить только затронутые факты и ссылки на доказательства.
4. Mock/unit-тест ≠ E2E-доказательство.
5. Не заявлять `РАБОТАЕТ` без свежего наблюдаемого результата.
6. Большие логи/screenshots — в `agents\artifacts`; в корневых документах — кратко + путь.
7. У каждого изменяемого факта в `UNI_STATUS.md` — дата проверки.
8. При конфликте документов приоритет — более свежему воспроизводимому runtime-доказательству; затем документы обновляются.
9. **Ничего не удалять физически**: убираемый фрагмент сохранять как `DEPRECATED by Hermes` с причиной/датой либо в соседний `*.deprecated`.
10. `capability` не импортирует `capability` (ADR-0005) — это ловит `uni.check_architecture`.
11. `mock ≠ E2E`; «РАБОТАЕТ» только со свежим наблюдаемым пруфом.

## Стратегическая цель

Довести dev-версию до подтверждённого E2E, затем создать самостоятельные `UNI-Launcher.exe`, `UNI-Setup.exe` и portable/offline пакет для Windows 10/11 x64. CPU — обязательный базовый профиль; GPU — проверенное ускорение с честным CPU fallback. Детали — в `UNI_PROJECT_BRIEF.md`.
