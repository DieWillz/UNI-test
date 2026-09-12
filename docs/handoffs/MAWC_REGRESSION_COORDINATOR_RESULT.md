# MAWC Regression Coordinator Result

AGENT: GPT UNI Multi-Agent Coordinator

STATUS: VERIFIED — regression discovery pass complete for this lane.

## CURRENT BASELINE

Full project pytest collection: 935 tests, 0 collection errors.

### PASSING GROUPS (вне operator lane)

- `tests/devcoord/` — **154 passed** (все тесты DevCoord пройдены включая test_direction_sync.py)
- `tests/council/` — (не запускались в этой смене, handoff Astra)
- `tests/` (все остальные, кроме operator/council) — **581 passed, 2 skipped**
- `tests/test_computer_vision_agent.py` + `tests/operator/test_computer_operator_surface.py` — **3 passed** (verified Astra)

### FAILING GROUPS

**Все failures находятся в operator lane (`uni/operator/`). НЕ исправляются Koординатором.**

#### Основные failures (3 реальных, воспроизводимых изолированно):

1. **`tests/operator/test_browser_execution_recovery.py::test_planner_browser_catalog_is_task_specific`**
   - TEST: `assert _estimate_tokens(catalog) < 1500`
   - ROOT CAUSE: `_catalog_text(scope="browser")` в `uni/operator/planner.py:185` возвращает 3589 токенов. Браузерный каталог содержит слишком много actions или схемы параметров слишком длинные, чтобы уложиться в budget 1500 токенов.
   - OWNER: Codex Astra / UNI Execution Core
   - FILES: `uni/operator/planner.py:185-205`, `tests/operator/test_browser_execution_recovery.py:77`
   - REPRO: `pytest -q tests/operator/test_browser_execution_recovery.py::test_planner_browser_catalog_is_task_specific`

2. **`tests/operator/test_browser_execution_recovery.py::test_planner_simple_browser_command_fits_context_budget`**
   - TEST: `planner._user_prompt(BROWSER_GOAL, scene=..., scope="browser", failure_context="")`
   - ROOT CAUSE: `AttributeError: 'MissionPlanner' object has no attribute '_user_prompt'`. Метод `_user_prompt` не реализован в `MissionPlanner`, хотя тест его ожидает.
   - OWNER: Codex Astra / UNI Execution Core
   - FILES: `uni/operator/planner.py`, `tests/operator/test_browser_execution_recovery.py:84`
   - REPRO: `pytest -q tests/operator/test_browser_execution_recovery.py::test_planner_simple_browser_command_fits_context_budget`

3. **`tests/operator/test_browser_permissions.py::test_hostile_dom_and_model_response_cannot_grant_upload_permission`**
   - TEST: `MissionPlanner(HostileBrain()).plan("Read this page", scene=scene)`
   - ROOT CAUSE: `PlanParseError: plan_format_repair_exhausted: plan_action_outside_supplied_catalog`. Модель пытается использовать action, который не в белом списке каталога.
   - OWNER: Codex Astra / UNI Execution Core
   - FILES: `uni/operator/planner.py:298-302`, `tests/operator/test_browser_permissions.py:34`
   - REPRO: `pytest -q tests/operator/test_browser_permissions.py::test_hostile_dom_and_model_response_cannot_grant_upload_permission`

#### Изолированные failures (test isolation issue):

**`tests/operator/test_agent_wiring.py::test_agent_owns_single_operator_runtime` и `::test_agent_operator_stop_uses_runtime_broker`**
- ROOT CAUSE: Эти 2 теста проходят изолированно (`pytest tests/operator/test_agent_wiring.py` → 2 passed), но падают при запуске вместе с другими operator тестами. Типичная проблема test isolation — возможно, загрязнение `asyncio` loop или глобального состояния между тестами.
- OWNER: Codex Astra / UNI Execution Core
- REPRO: `pytest -q tests/operator/` (все operator тесты вместе)

### CODEX TEST REQUESTS RESULTS
Нет активных запросов от Codex Astra. Файл `docs/handoffs/CODEX_ASTRA_TEST_REQUESTS.md` не создан.

### MAWC STATUS
- Active sessions: 1 (Coordinator — READY)
- Stale sessions: 0
- Active leases: 6 (исторические MAWC-owner-controls для DevCoord файлов)
- Conflict events: 0
- Ownership violations: 0

### BLOCKERS
1. **Controlled takeover contract** — не завершён для ACTIVE/VERIFYING задач (только stale/dead owner). Требует approved contract.
2. **FILE lease evidence contract** — base_hash/current_hash не всегда persistятся.
3. **3 реальных operator failures** — переданы Codex Astra.

### NEXT FAILURE
Следующий failure для Codex Astra:

```
tests/operator/test_browser_execution_recovery.py::test_planner_browser_catalog_is_task_specific
```

**Exact prompt for Codex Astra:**

```
TASK: Fix browser catalog token budget in MissionPlanner (operator lane).

FAILURE: tests/operator/test_browser_execution_recovery.py::test_planner_browser_catalog_is_task_specific
Root cause: `uni/operator/planner.py:185` method `_catalog_text(scope="browser")` 
returns 3589 tokens (limit: 1500). The browser-scoped catalog includes too many 
actions or schemas are too verbose.

Context:
- `_catalog_text()` filters registry by prefixes: ("operator.browser.", "browser.", "operator.desktop.")
- Each item includes: name, params (type+enum only), required, target, permission, postcondition
- FULL_CATALOG = all actions → browser catalog must be < 50% of full and < 1500 tokens

Also related: 
- test_planner_simple_browser_command_fits_context_budget fails: MissionPlanner 
  has no `_user_prompt` method (AttributeError)
- test_hostile_dom_and_model_response_cannot_grant_upload_permission fails: 
  PlanParseError plan_action_outside_supplied_catalog (model tries action not in catalog)

FIXES NEEDED (owner: Codex Astra / UNI Execution Core):
1. Reduce browser catalog to < 1500 tokens (review which operator.desktop.* 
   actions are needed in browser scope)
2. Add `_user_prompt(goal, scene, scope, failure_context)` method to MissionPlanner
3. Ensure hostile model actions not in catalog are rejected before plan_format_repair_exhausted

Repro: C:\LLM\python312\python.exe -m pytest -q --tb=short tests/operator/test_browser_execution_recovery.py tests/operator/test_browser_permissions.py
Run from: C:\LLM\UNI, PYTHONPATH=C:\LLM\UNI
```

### NEXT OWNER ACTION
- **Codex Astra**: Fix 3 реальных operator failures (browser catalog budget, _user_prompt method, hostile DOM rejection).
- **Codex Astra**: Investigate test isolation issue in test_agent_wiring.py (passes isolated, fails in group).
- **Astra**: Resume global regression from next real failure after operator fixes.
- **GPT UNI Multi-Agent Coordinator**: Continue from `tests/` (non-operator, non-devcoord, non-council) — 581 passed, 0 failures. All non-operator tests are green. Focus DevCoord lane на MAWC contract gaps (controlled takeover, FILE lease evidence).

## VERIFIED
- tests/devcoord/ — 154 passed (включая исправленный test_direction_sync.py)
- tests/ (non-operator, non-council) — 581 passed, 2 skipped
- devcoord test_direction_sync.py мигрирован на canonical uni.direction_sync (уже исправлен)
- Direction Sync ACK выполнен
- py_compile — OK
- git diff --check — OK (staged)
