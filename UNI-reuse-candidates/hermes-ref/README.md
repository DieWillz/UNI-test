# hermes-ref — референсные исходники Hermes Agent для анализа Юни

> Эта папка содержит **оригинальные исходники** движка Hermes Agent
> (которым управляет пользователь), сложенные сюда как **референс** для
> анализа другими ИИ. Проект Юни живёт в `C:\LLM\UNI\uni`.
>
> Источник: `C:\LLM\UNI\agents\uni-hermes\python-for-check\python-for-check\`
> (плоская выгрузка Hermes; оригинальная структура `hermes-agent/` была
> сплющена — подпапки `acp_adapter/`, `agent/`, `gateway/`, `tools/`,
> `hermes_cli/` воссозданы здесь вручную по назначению файлов).
>
> Дата выгрузки: 2026-08-13.

## ВАЖНО (для анализаторов)

1. **Это НЕ код Юни.** Это движок Hermes. Копировать файлами в `uni/` нельзя —
   они завязаны на `hermes_constants`, `hermes_cli.config`, `tools.tts_tool`
   и внутренности Hermes; в каноне Юни они сломаются.
2. **Брать как паттерны/референс:** архитектуру, подходы, контракты.
3. **Лицензия:** см. `AGENTS.md` / лицензию Hermes Agent. Заимствование —
   с учётом лицензии (пользователь подтвердил допустимость как референс).
4. `skills/` (вся папка навыков Hermes) в этой выгрузке **отсутствует**
   (плоская копия не содержит файлов со словом `skill`). Структуру навыков
   Юни (`uni/.../skills` или аналог) см. в каноне Юни, не здесь.

## Файлы и что в них полезно для Юни

| Файл (референс) | Оригинал в Hermes | Назначение | Польза для Юни |
|---|---|---|---|
| `acp_adapter/server.py` | `acp_adapter/server.py` | Реализация протокола ACP (Agent Communication Protocol) — мост агента с IDE (Zed, VS Code). | Интеграция Юни в IDE как локального оркестратора; UNI-in-the-IDE. |
| `acp_adapter/session.py` | `acp_adapter/session.py` | Сессия ACP (жизненный цикл диалога с редактором). | Модель сессии для встраивания Юни в редакторы. |
| `agent/conversation_loop.py` | `agent/conversation_loop.py` (`run_conversation`) | Основной цикл обработки диалога. | Референс для `uni/agent.py` / EventLoop Юни (цикл Намерение→План→Действие→Проверка→Коррекция). |
| `agent/context_compressor.py` | `agent/context_compressor.py` | Управление контекстом, сжатие при переполнении окна. | Долгие сессии Юни: сжатие истории (аналог WorkingMemory). |
| `agent/tool_executor.py` | `agent/tool_executor.py` | Система выполнения инструментов. | Архитектура ToolExecutor Юни (аналог скиллов/capabilities). |
| `agent/memory_manager.py` | `agent/memory_manager.py` | Управление памятью (краткосрочной/долгосрочной). | Референс для `uni/memory` Юни. |
| `agent/prompt_builder.py` | `agent/prompt_builder.py` | Сборка системного промпта. | Референс для ролевых промптов Юни (`role_prompt`). |
| `gateway/run.py` | `gateway/run.py` | Основной цикл шлюза (Telegram/Discord/Slack/…). | Мультиканальность Юни: адаптеры платформ. |
| `tools/registry.py` | `tools/registry.py` | Реестр инструментов. | Аналог `uni/capabilities` registry Юни (CapabilityRegistry). |
| `hermes_cli/config.py` | `hermes_cli/config.py` | Система конфигурации (Pydantic). | Референс для `uni/config.py` Юни (уже Pydantic). |
| `hermes_cli/auth.py` | `hermes_cli/auth.py` | Работа с учётками провайдеров (секреты). | Референс для secret-store Юни (без хардкода ключей). |

## Как анализировать

1. Читать файлы как есть (Python, читаемы).
2. Искать **паттерны**: цикл агента, сжатие контекста, реестр инструментов,
   мультиканальный шлюз, сборка промпта, управление памятью.
3. Не предлагать `import hermes_*` в Юни — только адаптацию логики.
4. Сверять с каноном Юни (`C:\LLM\UNI\uni`): `agent.py`, `brain.py`,
   `capabilities/`, `config.py`, `memory`, `webui/server.py`, `desktop/`.

## Мои (Hermes) комментарии

- `conversation_loop.py` + `context_compressor.py` — **самое ценное** для Юни
  (цикл диалога + сжатие истории). Юни уже имеет `agent.py`/`EventLoop`, но
  сжатие контекста в долгих сессиях — слабое место.
- `gateway/run.py` — полезен, если Юни нужна мультиканальность (сейчас только
  CLI/WebUI/Electron). Но это большой модуль (зависит от infra Hermes).
- `tools/registry.py` — концептуально совпадает с `CapabilityRegistry` Юни
  (ADR-0005: capability не импортирует capability).
- `skills/` отсутствует — навыки Юни живут в каноне, не в Hermes.

Hermes = Гермес, агент-координатор Юни. Подпись: 2026-08-13.
