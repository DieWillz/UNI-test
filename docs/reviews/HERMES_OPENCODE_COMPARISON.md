# Сравнение `uni/` (canonical, ADR-0001) и `Uni-OpenCode/uni/` (OpenCode)

> Отчёт подготовлен Hermes. Код НЕ исправляется, файлы OpenCode НЕ переносятся.
> Канонический источник по ADR-0001: `C:\LLM\UNI\uni`.
> Сравниваемая ветка: `C:\LLM\UNI\Uni-OpenCode\uni`.

## Легенда
- **Severity**: 🔴 critical / 🟠 high / 🟡 medium / 🔵 low
- **Решение**:
  - `REUSE` — идею/код можно взять в canonical как есть (возможно с доработкой);
  - `REWRITE` — идея ценна, но реализация сломана, нужна переписка;
  - `REJECT` — не брать.

---

## Сводная таблица архитектур

| Аспект | `uni/` (canonical) | `Uni-OpenCode/uni/` |
|---|---|---|
| Цикл | one-shot `run_cycle`/`run_interactive` | `run_cycle` + `run_continuous` + Planner |
| Планирование | нет (LLM сам выбирает tool_calls) | `PlannerImpl` → LLM JSON-plan → `TaskQueue` |
| Состояние | `AgentState` enum, но не используется | `AgentState` + `can_transition` машина состояний |
| Роли | нет | `RoleLoader` из Markdown |
| Маршрутизация | `ToolExecutor._ROUTING` dict | `ToolExecutor` → `capability.execute` напрямую |
| Vision | делает скриншот сама | принимает `image_base64` извне |
| Тесты | `test_planner_basic.py` (не читал глубоко) | `tests/integration/test_conversation.py` |

Вывод: OpenCode пошёл по пути «автономный агент с планировщиком», canonical — «простой голосовой цикл». Обе ветки **не реализуют ADR-0005 (Capability Router)**.

---

## Находки

### 1. Невозможные `depends_on`
- **Severity**: 🔴 critical
- **Файл/строки**: `Uni-OpenCode/uni/planner.py:98-110` (промпт требует `depends_on` как «ID предыдущих действий»), `:137-145` (создание `Task.id = uuid.uuid4()[:8]`).
- **Сценарий**: Planner просит LLM вернуть `depends_on` в виде «ID предыдущих действий», но сам генерирует `id` как случайный 8-символьный uuid **после** вызова LLM. LLM не знает реальных uuid → возвращает индексы `0,1,2...` или пустоту. Итог: `depends_on` никогда не совпадает с реальным `id` задачи.
- **Почему тесты не находят**: `test_conversation.py` не проверяет зависимости; требует живой LM Studio, где LLM «случайно» может вернуть пустой `depends_on` → баг молча проходит.
- **Переиспользование идеи**: концепт DAG-плана с зависимостями — хорош.
- **Решение**: `REWRITE`. Нужно либо генерировать стабильные id до вызова LLM (порядковые `t0,t1,...`) и просить LLM ссылаться на них, либо резолвить `depends_on` по индексу после парсинга.

### 2. Отсутствие `mark_completed`
- **Severity**: 🔴 critical
- **Файл/строки**: `Uni-OpenCode/uni/planner.py:56-58` (`TaskQueueImpl.mark_completed` определён, но **никем не вызывается`); `Uni-OpenCode/uni/event_loop.py:124-137` (после `_execute_task` задача не помечается выполненной, только добавляется в `action_history`).
- **Сценарий**: задача выполнена, но `self._completed` остаётся пустым. Любая последующая задача с `depends_on` никогда не увидит выполненную зависимость.
- **Почему тесты не находят**: тесты не создают планы с зависимостями и не проверяют `is_empty()` после выполнения.
- **Переиспользование идеи**: механизм `mark_completed`/completed-set полезен.
- **Решение**: `REUSE` (исправить вызов). В `run_cycle` после успешного `_execute_task` + verify нужно `await self.context.task_queue.mark_completed(task.id)`.

### 3. Зависание очереди
- **Severity**: 🔴 critical
- **Файл/строки**: `Uni-OpenCode/uni/event_loop.py:106-120`.
- **Сценарий**: `pop()` возвращает `None`, если нет PENDING-задачи с удовлетворёнными зависимостями. При этом `task_queue` не пуст (есть PENDING с невыполненными зависимостями, см. п.1+п.2). Код: `if not task: if is_empty(): ... else: await asyncio.sleep(0.5); return CONTINUE`. Результат — бесконечный цикл `CONTINUE`, агент «зависает», ничего не делая, CPU idle-спин.
- **Почему тесты не находят**: тесты не достигают этого состояния (планы без зависимостей проходят одним циклом).
- **Переиспользование идеи**: цикл `run_continuous` с лимитом `max_cycles` — ок.
- **Решение**: `REWRITE` (совместно с п.1, п.2). Без корректных зависимостей и `mark_completed` очередь нежизнеспособна.

### 4. Fail-open верификация
- **Severity**: 🟠 high
- **Файл/строки**: `Uni-OpenCode/uni/event_loop.py:205-233`, особ. `:207-208` (`if not verification_enabled: return True`), `:226-232` (парсинг `json.loads(verify_result["analysis"])`), `:233` (`return True`).
- **Сценарий**: верификация «успешна» по умолчанию, если (а) выключена, (б) vision недоступен, (в) VLM вернул JSON в markdown-обёртке ```json → `json.loads` падает → `except: pass` → возврат `True`. То есть агент считает действие выполненным, даже если оно провалилось (тот же класс бага, что в canonical `xtoys.toggle`).
- **Почему тесты не находят**: верификация по умолчанию `verification_enabled: True`, но требует живой VLM; при сбое парсинга тест всё равно получает `CycleResult` и проходит.
- **Переиспользование идеи**: концепт verify-after-action — ценен.
- **Решение**: `REWRITE`. Верификация должна быть **fail-closed**: при ошибке парсинга/нет ответа → `False`. Нужна очистка markdown-обёртки перед `json.loads` (как и в canonical, п. vision).

### 5. Dotted-name mismatch (имена `capability.action` ≠ ключи роутера)
- **Severity**: 🔴 critical
- **Файл/строки**: `Uni-OpenCode/uni/planner.py:105` (промпт: «name: capability.action»), `:134` и `:175` (fallback жёстко `"computer.screenshot_region"`), `Uni-OpenCode/uni/tools/definitions.py:50-81` (`TOOL_TO_CAPABILITY` с ключами **без точек**: `click`, `navigate`, …), `Uni-OpenCode/uni/event_loop.py:190-195` (`tool_name = task.action.name` → передаётся в `execute`).
- **Сценарий**: Planner выдаёт `"browser.click"`, но `get_capability_for_tool("browser.click")` возвращает `None` → `ToolExecutor` возвращает `{"success": False, "error": "Unknown tool: browser.click"}`. **Ни одна задача от Planner не выполняется**. Fallback в planner тоже сломан (точка в имени).
- **Почему тесты не находят**: тесты гоняют `run_cycle` с живым LLM; при ошибке `run_cycle` ловит Exception → `CycleResult.ERROR` → тест «проходит» (проверяет только тип).
- **Переиспользование идеи**: единый реестр tool→capability — хорош.
- **Решение**: `REWRITE`. Либо Planner генерирует имена без точек (`click`), либо `get_capability_for_tool` режет по точке. Fallback должен использовать валидное имя (`screenshot_region`).

### 6. Скрытый screenshot fallback
- **Severity**: 🟡 medium
- **Файл/строки**: `Uni-OpenCode/uni/event_loop.py:170-186` (`_observe` делает `computer.execute("screenshot_region", {})` и кладёт `screen_base64` в `context`), `:218-225` (verify тоже делает screenshot). При этом `run_cycle` **не передаёт** `screen_base64` в `planner.plan(...)` (см. `planner.py:119-122` — туда идёт только `goal` + `action_history`).
- **Сценарий**: захват экрана происходит, но не используется для планирования/наблюдения (только сохраняется в `context.screen_base64`, который нигде не читается). По сути мёртвый код + «запасной путь» захвата, который ничего не меняет.
- **Почему тесты не находят**: тесты не проверяют содержимое observation.
- **Переиспользование идеи**: включение скриншота в observation для VLM-планирования — ценно.
- **Решение**: `REUSE` (исправить связку). Передавать `screen_base64` в `planner.plan` как часть контекста наблюдения.

### 7. Сброс `max_replans` между целями
- **Severity**: 🟠 high
- **Файл/строки**: `Uni-OpenCode/uni/planner.py:82-83` (`self.current_replans = 0` в `__init__`), `:150-154` (`replan` инкрементирует и бросает `RuntimeError` при превышении), `Uni-OpenCode/uni/event_loop.py:96-99` (новый `user_input` меняет `current_goal` и чистит `action_history`, но НЕ сбрасывает `planner.current_replans`).
- **Сценарий**: после нескольких неудачных целей `current_replans` накапливается и никогда не обнуляется. На новой цели replan сразу падает с `RuntimeError` → агент говорит «Не удалось выполнить задачу» даже для простой новой команды.
- **Почему тесты не находят**: тесты шлют 4 разные команды подряд, но ни одна не доходит до `replan` (см. п.5 — tool-ы всё равно «Unknown»), так что ветка не тренируется.
- **Переиспользование идеи**: лимит replan на цель — правильно.
- **Решение**: `REWRITE` (исправление 1 строкой). Сбрасывать `planner.current_replans = 0` при смене `current_goal` в `run_cycle`.

### 8. Классификация ошибок не реализована
- **Severity**: 🟠 high
- **Файл/строки**: `Uni-OpenCode/uni/planner_interface.py:152-158` (`classify_error` и `retry_delay` — тела `...`), использование `planner.py:159` (`classify_error(...).value`).
- **Сценарий**: `classify_error` возвращает `None` (тело `...`), значит `.value` → `AttributeError`. Функция вызывается только в `replan`, поэтому баг проявляется редко, но ломает replan целиком. `retry_delay` (экспоненциальный backoff с джиттером) тоже не реализован, хотя упоминается в контракте.
- **Почему тесты не находят**: `replan` не вызывается в тестах (см. п.5, п.7).
- **Переиспользование идеи**: детерминированная классификация TRANSIENT/PERMANENT + backoff — ценна для отказа от бессмысленных ретраев.
- **Решение**: `REWRITE`. Реализовать `classify_error` (по подстрокам: `element_not_found`→TRANSIENT, `invalid_selector`→PERMANENT и т.д.) и `retry_delay`.

### 9. Обход Capability Router (ADR-0005)
- **Severity**: 🟡 medium
- **Файл/строки**: `Uni-OpenCode/uni/tools/executors.py:23` (`capability.execute(tool_name, args)` напрямую); canonical `uni/tools/executors.py:33` (через `_ROUTING` dict).
- **Сценарий**: обе ветки игнорируют ADR-0005 (capability-router). OpenCode зовёт `capability.execute(tool_name)` — но реализации capability (`browser.py`, `computer.py`) ожидают **имя своего внутреннего тула** (`_tool_<name>`), а не «capability.action». То есть связка planner→executor→capability разорвана (см. п.5).
- **Почему тесты не находят**: тесты не проверяют соответствие контракту роутинга.
- **Переиспользование идеи**: сам ADR-0005 (центральный Router) — стоит реализовать в canonical.
- **Решение**: `REJECT` текущей реализации; `REUSE` идеи ADR-0005 (создать единый `CapabilityRouter`, через который идут все вызовы, с валидацией имён).

### 10. Качество integration-тестов
- **Severity**: 🟠 high
- **Файл/строки**: `Uni-OpenCode/tests/integration/test_conversation.py:13-62`.
- **Сценарий**: тесты проверяют **только тип** возврата (`isinstance(result, CycleResult)`), не мокают LLM/браузер/голос, требуют живой LM Studio + Playwright + микрофон. Ни одна из находок выше (зависание, mismatch, fail-open) тестами не покрывается — они «проходят», потому что любой `CycleResult` (в т.ч. `ERROR`) удовлетворяет `isinstance`.
- **Почему тесты не находят**: по определению — они не assertion-ят поведение, только форму.
- **Переиспользование идеи**: наличие integration-скелета — ок, но нужны unit-тесты с моками.
- **Решение**: `REWRITE`. Добавить unit-тесты `TaskQueueImpl` (push/pop/mark_completed/depends_on), `PlannerImpl.plan` с моком Brain, `ToolExecutor` с моком capability. Без моков логика не тестируема.

### 11. Vision `image_base64`
- **Severity**: 🟡 medium
- **Файл/строки**: `Uni-OpenCode/uni/capabilities/vision.py:67-91` (`_tool_analyze_screen` берёт `args["image_base64"]` и оборачивает в `data:image/png;base64,{image_base64}` на `:76`); canonical `uni/capabilities/vision.py:22-46` (делает скриншот **сама** через `ImageGrab`).
- **Сценарий**: 
  - (а) Несовместимость контрактов: canonical Vision сама захватывает экран (`analyze_screen(prompt)`), OpenCode Vision требует `image_base64` извне. Если переиспользовать canonical `xtoys.get_status` (который зовёт `vision.analyze_screen(prompt)`) с OpenCode Vision — упадёт (`KeyError: image_base64`).
  - (б) Двойной префикс: если вызывающий передаст уже `data:image/png;base64,...`, строка `:76` сделает `data:image/png;base64,data:image/png;base64,...` → VLM получит битый URL.
- **Почему тесты не находят**: тесты не передают image в Vision напрямую (только через event_loop, где это тоже не покрыто assertion-ми).
- **Переиспользование идеи**: разделение «захват» и «анализ» (OpenCode) — чище, чем монолит canonical.
- **Решение**: `REUSE` (контракт OpenCode) + доработка: проверять, не начинается ли `image_base64` уже с `data:`, и унифицировать сигнатуру с canonical (либо обёртка-хелпер, либо canonical Vision принимает опциональный `image_base64`).

### 12. RoleLoader и зависимость от текущей директории
- **Severity**: 🟠 high
- **Файл/строки**: `Uni-OpenCode/uni/roles/loader.py:19` (`self.roles_dir = roles_dir or Path("roles")` — относительно CWD); `Uni-OpenCode/uni/agent.py:55-56` (`RoleLoader().load(config.agent.default_role)` без директории).
- **Сценарий**: роль грузится из `./roles/assistant.md` относительно **текущего каталога запуска**. Если запустить `python -m uni` не из `Uni-OpenCode/`, а из `Uni-OpenCode/uni/` или корня — `FileNotFoundError: Role not found: .../roles/assistant.md`. Canonical версия ролей вообще не имеет (agent.py canonical не загружает RoleLoader), так что это расхождение двух веток.
- **Почему тесты не находят**: тесты запускаются из корня проекта (где `roles/` есть), баг не проявляется.
- **Переиспользование идеи**: роли из Markdown — полезно, canonical этого не хватает.
- **Решение**: `REUSE` (идея) + фикс: `roles_dir` по умолчанию = `Path(__file__).parent.parent / "roles"` (как `load_config` в `config.py:122`), а не CWD.

---

## Что стоит взять из OpenCode в canonical (`REUSE`)
1. **Машина состояний** `state.py` (`can_transition`) — canonical `Agent.state` сейчас мёртв (см. находку в первом ревью). ✅
2. **`RoleLoader`** из Markdown (+ фикс CWD). ✅
3. **Vision, принимающая `image_base64`** (разделение capture/analyze). ✅
4. **`mark_completed` / completed-set** в очереди задач. ✅
5. **ADR-0005 Capability Router** (идея, не код). ✅

## Что НЕ брать (`REJECT` / ждёт `REWRITE`)
- Планировщик и TaskQueue в текущем виде (п.1–п.3, п.7) — сломаны, нужна переписка.
- Fail-open верификация (п.4) — инвертировать в fail-closed.
- Dotted-name конвенция (п.5) — сломана.
- `classify_error`/`retry_delay` (п.8) — не реализованы.
- Integration-тесты как есть (п.10) — бесполезны без unit+моков.

## Критические блокеры OpenCode (агент не работает впринципе)
- **п.5** (никто из tool-ов Planner не резолвится в `TOOL_TO_CAPABILITY`) ⇒ каждый цикл завершается `ERROR`/пустым результатом.
- **п.1+п.2+п.3** (зависание очереди) ⇒ при любой попытке использовать зависимости — бесконечный спин.

Canonical ветка при этом **запускается** (хоть и с ложным `success` в `xtoys.toggle`/`select_pattern` и багом парсинга vision, описанными в первом ревью), поэтому для продакшена сейчас ближе canonical, но с переносом идей state-machine/roles/router из OpenCode после их починки.
