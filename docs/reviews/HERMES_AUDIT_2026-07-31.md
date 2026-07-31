# Аудит проекта UNI (2026-07-31)

> Аудитор: Hermes. Объект: канонический пакет `C:\LLM\UNI\uni` в **текущем состоянии на диске**.
> Код НЕ изменялся в ходе аудита. Все ссылки — на реальные файлы/строки, прочитанные в этой сессии.

## 0. Что изменилось с начала сессии (важно)

Код на диске **существенно переписан** по сравнению с первым ревью:
- Появились `uni/browser_session.py` (persistent Chromium + `search_web`), `uni/visual_ui_operator.py`, `uni/session_log.py`, `uni/capabilities/camera.py`, `uni/roles/loader.py`.
- `event_loop.py` стал **реактивным** (regex `parse_direct_command` + `_free_form` через LLM), без Planner/TaskQueue.
- `xtoys` теперь с `max_intensity` (защитный лимит), `vision` — с безопасным парсингом JSON (`extract_json_value`) и нормализацией координат (`ElementLocation`).
- `working_memory` — с redaction секретов, диалоговым буфером, legacy-миграцией.

Это **хороший рост качества**. Но архитектура разошлась с `ARCHITECTURE.md`, и в дереве остался мёртвый/конфликтующий код старой ветки.

---

## 1. Критические находки

### 1.1 Мёртвый/конфликтующий код старой ветки в каноническом дереве
- **Файлы**: `uni/planner.py`, `uni/planner_interface.py`, `uni/uni/` (вложенный дубль пакета), `uni/backup/`, `tests/integration/test_conversation.py`.
- **Проблема**:
  - Актуальный `uni/agent.py` **не импортирует** `planner.py`; реальный цикл — `event_loop.py` (реактивный). То есть `planner.py` и `TaskQueueImpl`/`PlannerImpl` — **мёртвый код** в canonical-дереве.
  - Вложенный `uni/uni/` — это целый дубль пакета (agent/event_loop/capabilities/…). По ADR-0001 и BUILD_STATUS это нарушение («Duplicate package trees make accidental edits and imports likely»).
  - `tests/integration/test_conversation.py` импортирует `from uni.event_loop import CycleResult` — но в актуальном `event_loop.py` `CycleResult` **удалён** (теперь `run_cycle` возвращает `str | None`). ⇒ **тесты падают на импорте**, ещё до логики. При этом canonical-ветка их вообще не использует (BUILD_STATUS: «Tests blocked»).
- **Риск**: кто-то правит `uni/uni/agent.py` вместо `uni/agent.py` → тихо ломает прод; импорт-циклы; путаница в code-review.
- **Решение**: удалить `uni/uni/`, `uni/backup/`, `tests/` (или переписать под актуальный API), и либо удалить `planner.py`/`planner_interface.py` из canonical (они живут как reference в `Uni-OpenCode/`), либо оформить отдельным пакетом `uni/planner/` и реально подключить.

### 1.2 Отставание ARCHITECTURE.md от реальности
- `ARCHITECTURE.md` описывает `Planner → TaskQueue → CapabilityRouter → AgentContext`, а реализовано `parse_direct_command` (regex) + `_free_form` (LLM tool-calls) без Router/Context.
- ADR-0005 (CapabilityRouter) **не реализован**: `ToolExecutor._ROUTING` — статический dict (executors.py:9-30), это не Router из контракта.
- ADR-0004 (единые `Action`/`ActionResult`/`Observation`/`AgentContext`) — частично: есть `ToolResult` (contracts.py), но `Action`/`Observation`/`AgentContext` отсутствуют как типы; Planner-ветка использует свои датаклассы `Action`/`Task` (planner_interface.py), которые не совпадают с `ToolResult`.
- **Решение**: либо обновить ARCHITECTURE.md под фактическую реактивную архитектуру (честнее — MVP так и работает), либо принять ADR об отказе от Planner/TaskQueue в пользу реактивного цикла, и формализовать `ToolExecutor` как Router.

### 1.3 Нет защиты от «фантомного успеха» у XToys (остаточный риск)
- `xtoys.open` / `set_intensity` / `toggle` / `select_pattern` возвращают `verified: False` и явно пишут «состояние не подтверждено» (xtoys.py:83,115,146,162) — это **хорошо** (честно).
- Но `_free_form` (event_loop.py:190-197) берёт `final.text` как ответ пользователю и **не проверяет** `success` промежуточных tool-вызовов перед формулировкой итога; system-промпт просит «не выдумывать успех», но это мягкое требование к LLM, не жёсткий контроль.
- **Решение**: в `_free_form` передавать в финальный промпт явные метки `OK/FAIL` по каждому tool-вызову (уже есть `tool_summaries`), и запрещать фразы «готово/выполнено», если хоть один `success=False`.

---

## 2. Высокие находки

### 2.1 Зависимость запуска от venv Hermes (окруженческая ловушка)
- Терминал Hermes экспортирует `PYTHONPATH` на venv Python 3.14; `pydantic_core` оттуда не грузится под 3.12 → `ModuleNotFoundError: pydantic_core._pydantic_core`.
- **Решение**: добавить в `README`/`AGENTS.md` явную команду запуска — `py -3.12 -m uni` (как в `__main__.py` docstring) **без** активации venv Hermes, либо зафиксировать зависимости в `requirements.txt`/venv проекта и документировать `python312 -I`/isolated как fallback.

### 2.2 Headless/GUI-режим браузера
- `config.browser.headless` по умолчанию `False` (config.py:18). В headless-среде (CI, RDP без дисплея) Chromium падает с `Target page... has been closed` → `xtoys.open`/`search_web` → `success=False` (проверено в smoke).
- **Решение**: автодетект дисплея или флаг `--headless` по умолчанию для не-десктопных сред; в smoke это обошли `headless=True` в памяти.

### 2.3 `RoleLoader` загружается, но нигде не используется
- `agent.py` больше не строит роль (в отличие от OpenCode-версии). `RoleLoader` (roles/loader.py) — мёртвый импорт-кандидат. Сама роль `assistant.md` не применяется к промпту `_free_form`.
- **Решение**: либо подключить `role.system_prompt` в `_free_form` (ценно — даёт поведение/ограничения), либо удалить `roles/`.

### 2.4 `VisualUIOperator` и `camera` не зарегистрированы в `Agent`
- `Agent.__init__` регистрирует speech/computer/browser/vision/memory/xtoys, но **не** `camera` и не создаёт `VisualUIOperator`. Значит `VisionCapability.analyze_desktop`/`find_desktop_element` и вся desktop-автоматика недоступны из цикла, хотя код написан.
- **Решение**: подключить `CameraCapability` + `VisualUIOperator` в `Agent` (за конфиг-флагом), и добавить direct-команды (например, «найди окно X», «сделай фото»).

### 2.5 Безопасность: Telegram-автоматика с `requires_confirmation`
- `VisualUIOperator.draft_telegram_message` ставит `requires_confirmation=True`, но **нет механизма** подтверждения — `send_focused_draft` просто жмёт Enter (visual_ui_operator.py:223-234). По сути подтверждение декларативное, не принудительное.
- **Решение**: реальный hitl-барьер — отправка только после явной команды пользователя «отправь», и никогда автоматически. Это критично для безопасности (отправка сообщений third-party).

---

## 3. Средние находки

### 3.1 `ComputerCapability` монолит на 1035 строк
- Огромный класс: mouse/keyboard/clipboard/UIA/Telegram/браузер-фокус. Трудно тестировать и читать.
- **Решение**: разбить на `input/`, `window/`, `uia/`, `apps/` подмодули; `ComputerCapability` — фасад.

### 3.2 Дублирование `_SECRET_PATTERNS` / redaction
- Одинаковые регэкспы в `working_memory.py:17-21` и `session_log.py:12-16`.
- **Решение**: вынести в `uni/security/redact.py` (shared util).

### 3.3 `ToolRegistry` мёртв (tools/registry.py)
- `tools/registry.py` (`ToolRegistry`) нигде не используется; актуальная маршрутизация — `ToolExecutor._ROUTING` + `definitions.py`.
- **Решение**: удалить `tools/registry.py` или объединить с `ToolExecutor` (сделать его единым Router).

### 3.4 `tools/definitions.py` держит устаревшие имена
- `definitions.py` описывает `navigate`, `click_selector` и т.д., но реальные actions сейчас `browser.navigate`/`browser.search_web` и т.д. `get_tool_schemas` используется в `_free_form` (event_loop.py:170) — но описания могут не совпадать с зарегистрированными тулами capability (у capability свои `list_tools`? — `base.Capability` не имеет `list_tools`; registry `capabilities/registry.py` тоже нет). ⇒ **LLM получает схемы, которые не соответствуют реальным обработчикам**.
- **Решение**: генерировать схемы из самих capability (каждый capability знает свои actions), одним источником правды.

### 3.5 `extract_json_value` — хорошо, но доверяет `raw_decode` без ограничений
- vision.py:73-91 — корректно снимает markdown, но если VLM вернёт гигантский мусор до JSON, `raw_decode` возьмёт первый объект; это ок, но нет лимита размера/глубины.
- **Решение**: оставить как есть (уже лучше, чем было), добавить защиту от `NaN`/`Infinity` в координатах.

### 3.6 Нет таймаутов на внешние вызовы в `computer`
- `pyautogui.click` и т.п. в `asyncio.to_thread` без таймаута; если окно зависло — поток блокируется.
- **Решение**: оборачивать в `asyncio.wait_for(..., timeout=...)`.

---

## 4. Низкие / стиль

- `event_loop.py:170` `get_tool_schemas(set(self.capabilities.get_names()))` — но `get_tool_schemas` не принимает аргументов (definitions.py:290). ⇒ **NameError/TypeError в `_free_form` при реальном вызове с LLM!** Это баг: вызов `get_tool_schemas(set(...))` упадёт, т.к. сигнатура `(set) -> list` не совпадает. *Проверить и починить: либо убрать аргумент, либо сделать фильтрацию по именам capability внутри.*
- `config.py:load_config` не бросает `FileNotFoundError` (в отличие от OpenCode), а молча возвращает дефолт — удобно, но скрывает отсутствие `config.yaml`.
- `state.py` (`AgentState`) определён, но `EventLoop` импортирует его и использует только `self.state = AgentState.IDLE` — машина переходов из OpenCode не применена.
- Логирование: `SessionLogger` хороший, но не подключён к `EventLoop`/`Agent` (логирует только если кто-то вызовет). Подключить как observability.

---

## 5. Что уже сделано ХОРОШО (не трогать)

- ✅ `extract_json_value` + `ElementLocation` (безопасный парсинг/координаты Vision).
- ✅ `xtoys` с `max_intensity` и честным `verified: False`.
- ✅ `WorkingMemory` с redaction, диалоговым буфером, atomic `persist` (tmp+replace), legacy-миграцией.
- ✅ `SessionLogger` с redaction секретов.
- ✅ `BrowserSession` с persistent context и fallback channel (chrome→bundled).
- ✅ `CameraCapability` с явным `notice_ack` (согласие до включения камеры) — хорошая приватность-модель.
- ✅ Smoke-прогон (HERMES_FASTTRACK) подтвердил: LLM, TTS, XToys-open, web-search работают.

---

## 6. Варианты улучшений (предложения)

### Вариант A — «Почистить и формализовать текущую реактивную архитектуру» (рекомендую)
1. Удалить `uni/uni/`, `uni/backup/`, `tests/integration/test_conversation.py` (сломан), `tools/registry.py`, `planner.py`/`planner_interface.py` из canonical (оставить как reference в `Uni-OpenCode/`).
2. Обновить `ARCHITECTURE.md`: зафиксировать реактивный цикл `parse_direct_command` + `_free_form` + `ToolExecutor`(=Router) + `BrowserSession`. Принять ADR об отказе от Planner/TaskQueue для MVP.
3. Починить `get_tool_schemas(set(...))` (п.4.1) и сделать схемы единым источником из capability.
4. Подключить `RoleLoader` и `SessionLogger` в `Agent`/`EventLoop`.
5. Добавить unit-тесты (без браузера/LLM): `extract_json_value`, `parse_spatial_location`, `WorkingMemory.redact/append_exchange`, `EventLoop.parse_direct_command` (regex-команды), `ToolExecutor.canonical_name`.
- **Плюсы**: минимум риска, честно отражает работающий MVP, убирает мёртвый код.
- **Минусы**: не реализует «Plan → Verify → Recover» из ARCHITECTURE.

### Вариант B — «Довести до полной архитектуры (Planner + Router + Context)»
1. Взять `PlannerImpl`/`TaskQueueImpl` из OpenCode, **переписать** с учётом багов из `HERMES_OPENCODE_COMPARISON.md` (dotted-name, mark_completed, reset replans, classify_error).
2. Реализовать `CapabilityRouter` (ADR-0005) вместо статического `_ROUTING`.
3. Ввести `AgentContext` (Observation + ActionResult + goal state) — сериализуемый.
4. Сшить `EventLoop` с Planner для многошаговых сценариев (YouTube MVP).
- **Плюсы**: соответствует ARCHITECTURE.md и MVP-определению (verified playback, retry, hitl).
- **Минусы**: большой объём, высокий риск регрессий, требует стабильного LLM-планирования (сейчас qwen2.5-7b может давать нестабильные планы).

### Вариант C — «Гибрид: реактивный цикл + опциональный Planner для сложных целей»
1. Оставить `parse_direct_command` для одношаговых команд (быстро, надёжно).
2. Только если `_free_form` видит многошаговую цель (детектор по ключевым словам/LLM-классификатор), делегировать Planner.
3. Planner возвращает плоский список `capability.action` (без depends_on по умолчанию), исполняемый последовательно через `ToolExecutor` с verify после каждого шага.
- **Плюсы**: надёжность простых команд + масштаб сложных; зависимости не нужны (последовательность).
- **Минусы**: две ветки логики.

### Вариант D — «Операционная надёжность» (независимо от A/B/C)
- Таймауты на все внешние вызовы (`asyncio.wait_for`).
- Headless-автодетект.
- hitl-барьер на отправку сообщений/управление XToys (никогда авто-отправка).
- Единый `requirements.txt` + документированный запуск (`py -3.12 -m uni`).
- Подключить `SessionLogger` как observability по умолчанию.

---

## 7. Приоритетный план (если выбираем A + D — самый безопасный)

| Шаг | Действие | Сложность |
|---|---|---|
| 1 | Удалить `uni/uni/`, `uni/backup/`, `tests/integration/`, `tools/registry.py`, `planner*.py` из canonical | low |
| 2 | Починить `get_tool_schemas(set(...))` в event_loop.py:170 | low |
| 3 | Единый источник tool-схем из capability | medium |
| 4 | Подключить `RoleLoader` + `SessionLogger` | low |
| 5 | Таймауты + headless-автодетект + hitl на отправку/xtoys | medium |
| 6 | Unit-тесты (без браузера/LLM) | medium |
| 7 | Обновить ARCHITECTURE.md + ADR об отказе от Planner для MVP | low |

---

## 8. Итог

Проект **заметно продвинулся** и в рабочем состоянии для MVP-сценариев (smoke подтвердил). Главные риски сейчас — **не баги логики, а гигиена дерева** (мёртвый код старой ветки, сломанные тесты, отставание документации) и **пара конкретных дефектов** (`get_tool_schemas(set(...))`, неподключённые RoleLoader/SessionLogger/camera). Рекомендую **Вариант A + D**: почистить, починить точечные баги, формализовать фактическую архитектуру, добавить unit-тесты и операционную надёжность — без рискованного внедрения Planner.
