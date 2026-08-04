================================================================================
ПЛАН: DevCoord MVP + Knowledge Base (адаптация задания Qwen под реальный код)
Автор плана: Hermes
Дата: 2026-08-03
Основание: TASK_hermes_devcoord_knowledge_base.md (Qwen3.8, 2026-08-03)
Режим: DESIGN-FIRST — до одобрения пользователем код НЕ правится.
================================================================================

ВАЖНОЕ ПРЕДУВЕДОМЛЕНИЕ (прочитано перед планированием)
--------------------------------------------------------------------------------
Проверил реальный код. Три файла, которые Qwen прислал как «готовый код»
(aggregator.py, pipeline.py, council_bridge.py), написаны под ВЫМЫШЛЕННЫЙ API,
которого в проекте нет. Их нельзя просто скопировать — нужно ПЕРЕПИСАТЬ под
реальные модели. Конкретные расхождения:

  Qwen (в задании)                  Реально в uni/devcoord (проверено)
  ---------------------------------  ------------------------------------------------
  ProviderResult.response           ProviderResult.content
  ProviderResult.provider           ProviderResult.provider_id
  ProviderResult.confidence         поля НЕТ (нужно добавить, см. Фазу 2.1)
  Coordinator / DevTask             DevelopmentCoordinator / DevelopmentTask
  coordinator.run_all(task) -> list DevelopmentCoordinator.run_all(task_id: str)
                                    -> DevelopmentTask (results в task.results)
  DevTask(id,title,prompt,          DevelopmentTask(id,title,goal,instructions,
         target_files)              provider_sequence, ...)
  from .models import DevTask       from .models import DevelopmentTask

Поэтому ниже «интегрировать код Qwen» трактуется как «переписать под реальный
API, сохранив поведение из спецификации». uni/knowledge/base.py УЖЕ лежит в
репозитории и совместим (чистый SQLite + pydantic) — оставляем as-is.

================================================================================
ФАЗА 0 — Снять блокер check_architecture (1 коммит)
================================================================================
Диагноз (проверено):
  scripts/check_architecture.py --strict
    ERROR: uni/capabilities/computer.py: capability imports another capability:
           uni.capabilities.uni_action_badge
  check_architecture.py идёт по AST и ловит любой import из uni.capabilities.*
  внутри файла capabilities/. computer.py:50 делает:
      from uni.capabilities.uni_action_badge import UniActionBadge
  При этом uni_action_badge.py — УЖЕ обычный helper (class UniActionBadge, НЕ
  наследник Capability), он не регистрируется в Registry. Проблема чисто в том,
  что он лежит ВНУТРИ папки capabilities/.

РЕШЕНИЕ (рекомендую, вариант А-адаптированный):
  - Перенести uni/capabilities/uni_action_badge.py -> uni/action_badge.py
    (helper вне папки capabilities/ => сигнал «capability→capability» исчезает,
     и выполняется инвариант AGENTS.md «capabilities не импортируют другие
     capabilities напрямую»).
  - В computer.py:50 заменить
        from uni.capabilities.uni_action_badge import UniActionBadge
      на
        from uni.action_badge import UniActionBadge
  - Проверить search: в canonical uni/ uni_action_badge импортируется ТОЛЬКО из
    computer.py (подтверждено поиском). Других импортеров нет.
  - (опц.) поправить упоминание пути в uni/docs/AGENT_CURSOR.md:25 — не критично
    для гейта, сделаю, если не вызовет шума.

Альтернативы (на выбор пользователя):
  (Б) Оставить файл на месте, вынести создание бейджа в event_loop.py — сложнее,
      т.к. бейдж реально используется в computer.py (_flash_badge/click).
  (В) Whitelist в check_architecture.py (добавить uni_action_badge в
      разрешённые) — меняет утилиту, но не код; допустимо, но хуже по
      инвариантам, чем перенос.

Definition of Done Фазы 0:
  scripts/check_architecture.py --strict  ->  Summary: 0 error(s), 0 warning(s)
  (warning про вложенный uni/uni — это WARNING, не ERROR; 0 errors достигнуто)
  + smoke-тест Applier на тривиальном патче -> status="awaiting_human_confirmation"
    (уже покрыто существующим tests/test_devcoord_verifier_applier.py::
     test_applier_pass_awaits_and_never_commits; добавлю отдельный smoke при
     необходимости).

================================================================================
ФАЗА 1 — Knowledge Base (1 коммит: __init__ + тесты)
================================================================================
- uni/knowledge/base.py уже существует и корректен — НЕ меняем.
- Создать uni/knowledge/__init__.py (пустой) — делает пакет, чтобы
  pipeline.py мог делать `from ..knowledge.base import KnowledgeBase`.
- Расположение БД по DoD: .uni-dev/knowledge.db. В коде KnowledgeBase(db_path)
  принимает путь; тесты используют tmp_path. Реальный инстанс в pipeline/
  bridge будет создаваться с Path(".uni-dev/knowledge.db") (создам тонкий
  фабричный хелпер или просто передам путь в конструктор DevPipeline).
- Тесты tests/test_knowledge_base.py (6 шт, имена из задания), адаптированные
  под реальные поля моделей KnowledgeBase (response_text, verified,
  patch_success, source_task_ids, code_pattern, evidence):
    test_store_and_retrieve_response
    test_find_similar_filters_by_keywords
    test_mark_used_in_patch
    test_extract_skill
    test_get_top_skills_ordering
    test_store_and_get_claims
  Все на sqlite в tmp_path, без сети.

================================================================================
ФАЗА 2 — Aggregator + Pipeline + Bridge (3 коммита)
================================================================================
2.1 aggregator.py (ПЕРЕПИСАТЬ под реальный API)
  - from .models import ProviderResult (реальный).
  - В models.py ДОБАВИТЬ поле: confidence: float = 0.5  в ProviderResult
    (расширение, как делали с verified; нужно aggregator'у и KB).
  - ResponseCache/ResponseCache/aggregator.aggregate используют result.content
    и result.provider_id.
  - AggregatedResult.best_response: ProviderResult; alternatives: list.
  - Логика (из спецификации): кэш по (task_id, provider_id); бонус +0.2
    confidence провайдерам из successful_providers; дедуп по md5(content);
    выбор max по confidence. Сохраняю.

2.2 pipeline.py (ПЕРЕПИСАТЬ)
  - from .models import DevelopmentTask, ProviderResult
  - from ..knowledge.base import KnowledgeBase, CouncilResponse
  - DevPipeline.__init__(coordinator: DevelopmentCoordinator, verifier,
    aggregator, applier, knowledge_base)  — как в спецификации.
  - async process_task(task: DevelopmentTask) -> PipelineResult:
      1. task = await self.coordinator.run_all(task.id)   # реальный вызов
         results = task.results
      2. для каждого r в results: kb.store_response(CouncilResponse(
           response_id=f"{task.id}-{r.provider_id}", task_id=task.id,
           provider=r.provider_id, topic=task.title,
           response_text=r.content, confidence=r.confidence, verified=False))
      3. similar = kb.find_similar_responses(task.title, limit=3)
         successful_providers = {r.provider for r in similar
                                 if r.used_in_patch and r.patch_success}
      4. verified_results = [r for r in results
                             if r.verified and r.verified.verified]
         (при верифицированных — повторный store_response с verified=True +
          verification_evidence=r.verified.evidence)
         если пусто -> PipelineResult(status="failed_no_verified_responses")
      5. aggregated = self.aggregator.aggregate(task.id, verified_results,
                                                successful_providers=...)
      6. applied = await self.applier.apply_and_test(
           task.id, aggregated.best_response.content)
      7. если applied.status == "awaiting_human_confirmation":
           kb.mark_used_in_patch(f"{task.id}-{best.provider_id}", success=True)
      8. return PipelineResult(...)

2.3 council_bridge.py (ПЕРЕПИСАТЬ)
  - from .models import DevelopmentTask
  - from .pipeline import DevPipeline, PipelineResult
  - CouncilBridge(pipeline, tasks_dir, provider_sequence: list[str])  # откуда
    брать провайдеров — см. РЕШЕНИЕ#ниже.
  - async handle_council_topic(topic, brief):
      если не topic.startswith("dev-task:"): return None
      task = DevelopmentTask(
          id=f"DEV-{uuid...}", title=описание, goal=описание,
          instructions=brief, provider_sequence=self.provider_sequence)
      сохранить tasks_dir/<id>.json (task.model_dump())
      return await self.pipeline.process_task(task)
  - ЖИВАЯ интеграция с Council (SSE) НЕ делается: server.py и uni/council/*
    запрещено трогать по жёстким рамкам. Bridge = библиотека + юнит-тест.
    Реальное подключение к SSE — отдельный ADR/задача (см. Решения).

Тесты tests/test_devcoord_pipeline.py (6 шт):
  test_aggregator_deduplicates_by_hash
  test_aggregator_uses_cache
  test_aggregator_bonuses_successful_providers
  test_pipeline_stores_responses_in_kb
  test_pipeline_uses_similar_responses
  test_council_bridge_creates_task
  Все на стабах (FakeCoordinator/FakeProvider/FakeKB/Applier-заглушка), без сети.

================================================================================
ФАЗА 3 — CLI + интеграция (1–2 коммита)
================================================================================
- uni/knowledge/__main__.py:
    list-skills | search "..." | export-skills
    (читает .uni-dev/knowledge.db через KnowledgeBase).
- uni/devcoord/__main__.py:
    confirm <task_id>  -> Applier.confirm_merge(task_id)
  ВАЖНО: confirm_merge требует, чтобы Applier.apply_and_test отработал в ТОМ ЖЕ
  инстансе (хранит _last_base). CLI-инстанс создаёт свой Applier c тем же
  repo_root -> _last_base будет None (apply не запускался в этом процессе).
  РЕШЕНИЕ: confirm_merge должен определять base-ветку сам (например, текущая
  ветка != review/<id>, или сохранять base в файл при apply). План: добавить
  в Applier запись base-ветки в .uni-dev/review_base_<task_id>.txt при
  apply_and_test, и confirm_merge читает её. (Уточнить при реализации — см.
  Решения#4).

================================================================================
РЕШЕНИЯ ДЛЯ СОГЛАСОВАНИЯ (расхождения с DoD задания)
================================================================================
1) Параллельность >=3 провайдеров.
   DoD: «Pipeline обрабатывает задачу через >=3 провайдеров параллельно».
   Реально: DevelopmentCoordinator.run_all идёт ПОСЛЕДОВАТЕЛЬНО по
   provider_sequence. Параллелизм требует правки coordinator (отдельная задача).
   Рекомендую: сейчас оставить последовательно, пункт DoD отметить как
   «последовательно; параллелизм — отдельный ADR». Не править coordinator
   в рамках этого задания (одна задача = одно изменение).

2) patch_success строго ПОСЛЕ confirm_merge.
   Pipeline помечает used_in_patch на awaiting (ветка уже зелёная, ждёт только
   подтверждения). Пометка patch_success=True «после merge» технически требует
   хука после человеческого confirm_merge. Рекомендую: pipeline ставит
   used_in_patch=True + patch_success=True на awaiting (оптимистично), либо
   добавить DevPipeline.mark_patch_success(task_id) для вызова после confirm.
   Нужно уточнить у пользователя.

3) Живая интеграция Bridge <-> Council.
   server.py / uni/council/* — в «НЕ трогать». Значит bridge реализуем и тестим
   как библиотеку; реальное подключение к SSE оставляем вне scope (нужен ADR).
   ОК?

4) Фикс computer.py.
   Подтверждаешь перенос uni_action_badge.py -> uni/action_badge.py (рекомендую)
   или whitelist в check_architecture.py?

5) CLI confirm_merge: base-ветка между процессами.
   Нужно ли сохранять base-ветку на диск при apply_and_test, чтобы CLI
   confirm_merge (отдельный процесс) знал, куда мержить? Рекомендую да
   (.uni-dev/review_base_<id>.txt).

================================================================================
ПОРЯДОК КОММИТОВ (один коммит = одно изменение)
================================================================================
  C1 Фаза0: перенос uni_action_badge.py -> uni/action_badge.py + правка
            computer.py:50 (+doc AGENT_CURSOR.md опц.)
  C2 Фаза0: подтверждение гейта (check_architecture 0 errors) — фиксируется
            в AI_WORKLOG; smoke-тест Applier уже есть.
  C3 Фаза1: uni/knowledge/__init__.py + tests/test_knowledge_base.py
  C4 Фаза2: models.py (confidence) + uni/devcoord/aggregator.py
  C5 Фаза2: uni/devcoord/pipeline.py
  C6 Фаза2: uni/devcoord/council_bridge.py + tests/test_devcoord_pipeline.py
  C7 Фаза3: uni/knowledge/__main__.py + uni/devcoord/__main__.py (confirm с
            сохранением base-ветки)
  C8 AI_WORKLOG.md: запись на каждую фазу (подпись Hermes = ... от 2026-08-03)

================================================================================
ПРОВЕРКА (что запущу в конце каждой фазы)
================================================================================
  Фаза0: scripts/check_architecture.py --strict        -> 0 error(s)
  Фаза1: pytest tests/test_knowledge_base.py -q        -> 6 passed
  Фаза2: pytest tests/test_devcoord_pipeline.py -q     -> 6 passed
  Фаза3: python -m uni.knowledge list-skills
          python -m uni.knowledge search "retry"
          python -m uni.knowledge export-skills > skills.md
          python -m uni.devcoord confirm <id>  (на тестовой review-ветке)
  Итог:  pytest tests/test_knowledge_base.py tests/test_devcoord_pipeline.py -q
         + существующие tests/test_devcoord_verifier_applier.py (регрессия)

================================================================================
РИСКИ
================================================================================
- Основной объём — не копипаст, а переписывание aggregator/pipeline/bridge под
  реальный API. Поведение из спецификации сохраняется.
- confirm_merge в отдельном процессе (CLI) требует передачи base-ветки (Решение#5).
- Живая привязка Bridge к Council отложена (запрещённые файлы) — это не баг,
  а соблюдение жёстких рамок задания.
================================================================================
Hermes = план адаптации DevCoord MVP + Knowledge Base под реальный код,
подготовлен от 2026-08-03 (ждёт одобрения пользователя перед правкой кода)
================================================================================
