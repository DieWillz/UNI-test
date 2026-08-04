# Задание для Hermes: Verifier + Applier (расширение devcoord, НЕ пересборка)

## Контекст (прочитать перед тем, как писать код)

Проверено вживую 2026-08-03:
- `uni/contracts.py` — единый канонический `ToolResult`, дублей нет.
- `uni/planner.py` / `planner_interface.py` — мёртвый код, 0 ссылок в рантайме. Не трогать, не переиспользовать.
- `uni/tools/executors.py:57` — `_API_ALIASES` уже унифицирует dotted/underscore имена.
- `uni.webui` реально поднят, `/api/participants` отдаёт настоящие данные (browser-участники видят открытые вкладки через CDP).
- `devcoord/models.py`, `devcoord/coordinator.py`, `devcoord/providers.py`, `devcoord/store.py` — уже существуют и работают (`DevelopmentTask`, `CoordinationStore`, `DevelopmentCoordinator`, `ProviderRegistry`), сквозной тест create_task→store→fetch пройден.
- `scripts/dev_panel.py` и консоль (`uni/webui/index.html`, `script.js`, `style.css`) уже подключены к этому `devcoord` и работают через реальные endpoint'ы (`/api/round/start` SSE, `/api/config`, `/api/history`, `/api/report`).

## Задача (одна задача = одно изменение, по AGENTS.md)

Добавить в **существующий** `devcoord/` два новых модуля. Не создавать параллельный пакет, не переопределять `DevelopmentTask`/`CoordinationStore`/`ProviderRegistry` — импортировать их из текущих файлов.

### 1. `devcoord/verifier.py`

Задача: проверять утверждения ИИ о коде через реальный поиск по репозиторию (grep/AST), а не верить тексту ответа на слово.

```python
from uni.devcoord.models import DevelopmentTask

class ClaimVerificationResult(BaseModel):
    claim: str
    verified: bool
    evidence: str  # что реально нашли (строка/файл) или почему не подтвердилось
    checked_at: str

class Verifier:
    def __init__(self, repo_root: Path): ...

    def verify_claim(self, claim: str, file_hint: str | None = None) -> ClaimVerificationResult:
        """
        Пример: claim = "функция _API_ALIASES уже существует в executors.py"
        -> ищет паттерн в реальных файлах, возвращает verified=True/False с evidence.
        НЕ принимает утверждение на веру только потому, что его высказала модель
        с высокой уверенностью — ровно та ошибка, которую мы уже поймали на
        споре Hermes vs Copilot про config.py.
        """
```

Интеграция: `DevelopmentCoordinator` (существующий) получает опциональный вызов `verifier.verify_claim(...)` после получения ответа от провайдера, результат кладётся в `DevelopmentTask.results[i].verified` (расширить `ProviderResponse`/аналог поля в `models.py` одним полем `verified: ClaimVerificationResult | None`, не переписывать модель целиком).

### 2. `devcoord/applier.py`

Задача: применять предложенный код в отдельной git-ветке, прогонять тесты — **и останавливаться перед коммитом**.

```python
class ApplyResult(BaseModel):
    branch: str
    diff: str
    tests_passed: bool
    test_output: str
    status: str  # "awaiting_human_confirmation" | "reverted" | "merged"

class Applier:
    def __init__(self, repo_root: Path): ...

    async def apply_and_test(self, task_id: str, patch: str) -> ApplyResult:
        """
        1. git checkout -b review/<task_id>
        2. применить patch
        3. pytest -q && python scripts/check_architecture.py
        4. если тесты упали -> git checkout - && git branch -D (откат), status="reverted"
        5. если тесты прошли -> status="awaiting_human_confirmation", НЕ коммитить
           и НЕ мержить в основную ветку без отдельного явного вызова confirm_merge()
        """

    async def confirm_merge(self, task_id: str) -> bool:
        """Вызывается ТОЛЬКО человеком через консоль/CLI, не автоматически."""
```

**Жёсткое ограничение, не подлежит обсуждению:** `apply_and_test` никогда не коммитит и не мержит сам. Ветка `review/<task_id>` остаётся до тех пор, пока человек не вызовет `confirm_merge()` явно. Если Hermes считает, что можно обойтись без этого шага для «простых» патчей — не обходить: причина зафиксирована в плане (противоречащие фактические утверждения разных ИИ об одном и том же коде уже проверенный, не гипотетический риск).

## Что НЕ трогать

- `uni/webui/index.html`, `script.js`, `style.css`, `scripts/dev_panel.py` — не редактировать, не переименовывать, не создавать альтернативные версии.
- `devcoord/models.py`, `coordinator.py`, `providers.py`, `store.py` — только импортировать и расширять полями, не переписывать классы заново.
- `uni/planner.py`, `planner_interface.py` — не оживлять, не переиспользовать под Verifier/Applier.
- Не создавать `devcoord/dispatch.py`, `devcoord/cli.py`, `devcoord/providers/openai_compat.py` — `ProviderRegistry` и рассылка задач уже есть в `coordinator.py`/`providers.py`, дублирование создаёт тот самый «второй контур управления», который сам же Hermes определил как проблему.

## Проверено (заполнить после реализации, по вашему шаблону из AI_WORKLOG.md)

```
<команда> → <результат>
```

## Что должен сделать человек

Подтвердить/отклонить первый вызов `confirm_merge()` вручную, посмотрев diff и вывод тестов — не автоматически.

Hermes = <заполнить после выполнения>
