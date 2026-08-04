# UNI · Общий журнал работ ИИ

> **Назначение.** Единая точка правды: кто, когда и что менял в проекте.
> Пишут сюда **все** ИИ (Hermes, Grok, DeepSeek, QWEN, Claude, ChatGPT, Gemini…),
> чтобы не переделывать чужое и не затирать рабочие правки.
>
> Координатор — пользователь. Он переносит текст между ИИ.

---

## 📌 Правила ведения (обязательны для всех ИИ)

1. **Новая запись — сверху** блока «Хронология», сразу под заголовком. Свежее первым.
2. **Каждая запись подписывается** на отдельной строке в конце:
   `Hermes = <что сделано> от <дата>`
   Подписи предшественников **сохраняются**, а не затираются.
3. **ИИ-правки помечаются** 🤖 AI-правка.
4. Указывать **конкретные пути файлов**, а не «поправил вебуи».
5. Обязательно писать раздел **«Проверено»** — какие команды запускались и что вернули.
   Утверждение «работает» без вывода команды не принимается.
6. Если правка **отменяет или заменяет** чужую — явно назвать чью и почему.
7. Незавершённое пишем в **«Открытые вопросы»** внизу, а не молча бросаем.
8. **Секреты (API-ключи) в этот файл не попадают.** Только имя эндпоинта и статус.

### Шаблон записи

```markdown
### YYYY-MM-DD HH:MM · <Имя ИИ> · <краткая тема>

**Задача:** зачем это делалось.

**Изменённые файлы:**
| Файл | Что сделано |
|------|-------------|
| `path/to/file.py` | ... |

**Проверено:**
```
<команда> → <результат>
```

**Что должен сделать человек:** ...

<Имя> = <что сделано> от <дата>
```

---

### 2026-08-03 20:15 · Hermes · SafetyGuard → заглушка (физический пульт = контроль у пользователя) + XToys-панель

**Задача (1):** ПОЛНАЯ зачистка `uni/safety.py` — убрать всю «защиту от самого себя».
Пользователь подтвердил: есть физический пульт → нет аварийных стопов, лимитов,
таймеров, стоп-слов, NSFW-гейтов. Остался ТОЛЬКО whitelist автономии (логика, не безопасность).

**Задача (2):** WebUI-панель управления XToys (slash-команды + кнопки), адаптировано
под реальный `XToysCapability` (нет vibe/stop/pattern → set_intensity/select_pattern).

**Изменённые файлы:**
| Файл | Что сделано |
|------|-------------|
| `uni/safety.py` | Переписан в заглушку: `validate_tool`→`(True,"")`, `contains_safeword`→`False`, `session_check`→`(True,"")`, `autonomy_tools` whitelist по уровням. |
| `uni/config.py` | `SafetySettings`: только `autonomy_level` (убраны `max_intensity`/`max_session_minutes`/`nsfw_*`/`autonomy_interval`). |
| `config.yaml` | `safety:` → только `autonomy_level: "off"`. |
| `uni/agent.py` | `self.guard = SafetyGuard(SafetyConfig(**config.safety.model_dump()))` (без max_intensity-согласования, без `start_session`). |
| `uni/event_loop.py` | Убран guard из `_run_tool`; убраны `ctrl.emergency_stop()` по стоп-слову в `run_cycle`/`run_interactive`/`_maybe_autonomous_override` (стоп-слово только завершает диалог). |
| `uni/autonomous.py` | Убрано согласование `max_intensity` с guard (только `config.capabilities.xtoys.max_intensity`). |
| `uni/capabilities/camera.py` | (ранее) `start()` без `notice_ack`; маршрут `/api/camera/notice` удалён. |
| `uni/webui/server.py` | Удалён `/api/emergency` + `_handle_emergency`; `/api/safety` GET/POST без лимитов; ДОБАВЛЕН `/api/xtoys` + `_handle_xtoys` (oscillate→ramp_intensity, stop→set_intensity 0, macro→select_pattern; через `asyncio.run`, `agent.capabilities.get("xtoys")`). |
| `uni/webui/chat.html` | Панель «Автономность» (без кнопки ЭКСТРЕННЫЙ СТОП и ползунка лимита); ДОБАВЛЕНА панель «Управление XToys». |
| `uni/webui/chat.js` | `refreshSafety` без лимитов; slash-команды `/oscillate /stop /macro` в `send()`; XToys-панель handlers. |
| `uni/capabilities/xtoys.py` | Убран кламп `max_intensity` в `set_intensity` (п.4 ТЗ: «как попросили — так и шлём»). |
| `tests/test_safety.py` | Переписан под заглушку (4 теста). |
| `tests/fasttrack/test_camera.py` | `test_camera_starts_without_notice` (снят гейт notice). |
| `tests/fasttrack/test_xtoys_dom.py` | `test_maximum_reaches_ui_without_clamp` (кламп снят). |

**Проверено:**
```
py_compile uni/safety.py uni/config.py uni/agent.py uni/event_loop.py uni/autonomous.py uni/webui/server.py uni/capabilities/xtoys.py uni/capabilities/camera.py → OK
scripts/check_architecture.py --strict → 0 error(s), 0 warning(s)
node --check C:/LLM/UNI/uni/webui/chat.js → JS SYNTAX OK
pytest tests/test_safety.py → 4 passed
pytest tests/fasttrack/test_camera.py tests/test_safety.py tests/fasttrack/test_xtoys_dom.py → 15 passed
pytest tests/ → 160 passed + 7 subtests; 1 pre-existing fail (council/test_webui.py::test_frontend_roll_call_has_no_removed_notice_dependency — падает на index.html Council GUI, НЕ моя зона)
```
🤖 AI-правка. Hermes = SafetyGuard заглушка + XToys-панель (адаптировано под реальную архитектуру) от 2026-08-03 20:15

---

**Задача:** по ТЗ пользователя (Qwen-код, адаптированный) вшить SafetyGuard — кодовые
пределы безопасности (лимит интенсивности XToys, стоп-слово, таймер сессии, whitelist
автономии, NSFW_FORBIDDEN). Пользователь ПЕРЕОПРЕДЕЛИЛ: снять ВСЕ разрешительные гейты
(nsfw_enabled/nsfw_ack/allow_camera_nsfw, notice_ack камеры) — камера и NSFW-роли работают
без подтверждений; оставить только физические пределы.

**Изменённые файлы:**
| Файл | Что сделано |
|------|-------------|
| `uni/safety.py` (новый) | `SafetyGuard` + `SafetyConfig`: лимит интенсивности, whitelist автономии (`AUTONOMY_LEVELS`), `NSFW_FORBIDDEN`, стоп-слово, таймер сессии. БЕЗ nsfw-гейтов. |
| `uni/config.py` | `SafetySettings` (max_intensity, max_session_minutes, autonomy_level, autonomy_interval) + поле `safety` в `Config`. |
| `config.yaml` | блок `safety:` (max_intensity: 50, autonomy_level: off). |
| `uni/roles/loader.py` | поле `nsfw: bool` в `Role` + парсинг frontmatter. |
| `uni/roles/domina.md` (новый) | NSFW-роль 18+, консенсус, frontmatter `nsfw: true`. |
| `uni/agent.py` | `self.guard = SafetyGuard(...)`, согласование `max_intensity = min(safety, xtoys)`; `emergency_stop()` метод. |
| `uni/event_loop.py` | `guard.validate_tool` в `_run_tool` (центральная точка всех tool-calls). |
| `uni/autonomous.py` | автостарт камеры при autonomy_level != off; `max_intensity` согласован с guard. |
| `uni/capabilities/camera.py` | `start()` больше не требует `notice_ack` (гейт снят). |
| `uni/webui/server.py` | убран маршрут `/api/camera/notice` + гейт 403; маршруты `/api/safety` (GET/POST) + `/api/emergency`. |
| `uni/webui/chat.html/js/css` | панель «Автономность / Лимиты» (без NSFW-чекбоксов), убрана кнопка «🔔 Уведомить». |
| `tests/test_safety.py` (новый) | 5 тестов на гарантии guard. |
| `tests/fasttrack/test_camera.py` | обновлён тест под снятый гейт (`test_camera_starts_without_notice`). |

**Проверено:**
```
py_compile uni/safety.py uni/config.py uni/agent.py uni/event_loop.py uni/autonomous.py uni/roles/loader.py uni/webui/server.py uni/capabilities/camera.py → OK
scripts/check_architecture.py --strict → 0 error(s), 0 warning(s)
node --check C:/LLM/UNI/uni/webui/chat.js → JS SYNTAX OK
pytest tests/test_safety.py → 5 passed
pytest tests/fasttrack/test_camera.py tests/test_safety.py → 9 passed
pytest tests/ → 160 passed + 7 subtests; 1 pre-existing fail (council/test_webui.py::test_frontend_roll_call_has_no_removed_notice_dependency — падает на index.html Council GUI, НЕ моя зона, не трогал)
smoke: SafetyGuard.validate_tool(xtoys.set_intensity 100) → отказ; (40) → OK; NSFW computer.type → отказ; domina.md loader nsfw=True
```
🤖 AI-правка. Hermes = вшит SafetyGuard (без разрешит. гейтов, по переопределению пользователя) от 2026-08-03 18:50

### 2026-08-03 17:35 · Hermes · MVP: плавная мышь + XToys + чат-хаб (WebUI/Camera/Context Feed)

**Задача:** по двум ТЗ пользователя («MVP xtoys browser mouse» и «Чат-интерфейс,
Камера, Context Feed») реализовать: (а) плавное «живое» управление курсором и
демо «игрушки Uni» в браузере; (б) мультимодальный чат-хаб в WebUI с камерой,
голосом и внешними источниками стиля. ВАЖНО: оба ТЗ описывали ВЫМЫШЛЕННЫЙ
репозиторий (FastAPI webui/app.py, Uni/motion/, Uni/vision/camera.py, Uni/brain/).
Реальный код уже содержит аналоги — реализация сделана ОРКЕСТРАЦИЕЙ существующих
capability + добавлением новых модулей, БЕЗ дублирования (правило «без дублей»).

**Изменённые/новые файлы:**
| Файл | Что сделано |
|------|-------------|
| `uni/motion/trajectory.py` 🤖 | чистая математика плавных траекторий (Безье/easing/гуляние/круг) — без GUI |
| `uni/motion/driver.py` 🤖 | `SmoothMouseDriver` поверх pyautogui (failsafe=True, плавный заезд) |
| `uni/motion/label.py` 🤖 | `CursorLabelOverlay` — tkinter-подпись «Uni» у курсора (отдельный поток) |
| `uni/motion/__init__.py` 🤖 | экспорты пакета |
| `uni/scenarios/xtoys.py` 🤖 | демо `python -m uni --demo xtoys` (переписано под реальный Agent/CapabilitiesRegistry) |
| `uni/scenarios/__init__.py` 🤖 | пакет сценариев |
| `uni/context/feed_injector.py` 🤖 | `ContextFeedInjector` — сбор стилевых подсказок из фидов (внешний текст=не доверенный) |
| `uni/context/__init__.py` 🤖 | пакет |
| `uni/config.py` 🤖 | +`DemoXToysSettings`/`DemoMouseSettings`/`DemoSettings`/`ContextFeedConfig`; поля `Config.demo`/`Config.context`; **восстановлен** случайно удалённый `browser` в `CapabilitiesConfig` |
| `uni/capabilities/camera.py` 🤖 | +`capture_base64_frame()` (additive; не обходит гейт notice_ack) |
| `uni/webui/server.py` 🤖 | маршруты `/chat`, `/api/chat`, `/api/camera/{notice,start,stop}`, `/api/vision/capture`, `/api/context/feed` (один сервер :8787) |
| `uni/webui/chat.html` 🤖 | новый самодостаточный чат-хаб (не трогает index.html пользователя) |
| `uni/webui/chat.css` 🤖 | стили чат-хаба |
| `uni/webui/chat.js` 🤖 | логика чат-хаба (микрофон, камера, фиды) |
| `uni/__main__.py` 🤖 | флаг `--demo xtoys` |
| `tests/test_motion_trajectory.py` 🤖 | юнит-тесты траекторий |
| `tests/test_feed_injector.py` 🤖 | тесты feed_injector + санитайз (XSS-теги удаляются) |
| `tests/test_camera_base64.py` 🤖 | тест кодирования кадра в JPEG-base64 (без камеры) |
| `.hermes/desktop-attachments/План выполнения MVP xtoys browser mouse (Hermes).txt` 🤖 | детальный план + grounding в реальный код |

**Безопасность (сохранена жёстко):** XToys-ramp не выше `min(25, max_intensity)`,
`verified_physical` не включается; `pyautogui.FAILSAFE=True`; камера требует
звукового `notice` ДО старта (проверено: `start` без notice → 403); внешний
скрейп NSFW по умолчанию ВЫКЛ; один сервер на 8787, index.html пользователя не тронут.

**Проверено:**
```text
PYTHONPATH=C:\LLM\UNI C:\LLM\python312\python.exe -m pytest tests/test_motion_trajectory.py tests/test_feed_injector.py tests/test_camera_base64.py -q
→ 15 passed in 3.32s

scripts/check_architecture.py --strict  →  Summary: 0 error(s), 0 warning(s)

PYTHONPATH=C:\LLM\UNI C:\LLM\python312\python.exe -m py_compile <все изменённые .py>  →  ALL COMPILE OK

# живой сервер на :8787 (один процесс, без дублей):
GET  /chat                     → 200
GET  /api/context/feed         → 200 {"enabled":false,...,"feeds":[]}
POST /api/context/feed {add, hints} → 200, фид добавлен
POST /api/chat {"text":"привет юни..."} → 200 {"text":"Привет! Меня зовут UNI — я голосовой помощник...","audio_url":null}
POST /api/camera/start {}      → 403 {"error":"camera notice required first"}   # гейт работает
POST /api/camera/notice        → 200 {"noticed":true}
POST /api/vision/capture       → 409 (камера не включена — без обхода гейта)
```

**Что должен сделать человек (на машине запуска):** скопировать папку `uni/` целиком;
запустить `cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m uni --webui`,
открыть `http://localhost:8787/chat`. Для демо мыши/игрушек: `python -m uni --demo xtoys`
(на машине с экраном/камерой/xtoys). Для реального голоса и камеры — включить
`config.context.enabled` и нажать «🔔 Уведомить» перед камерой.

**Открытые вопросы:** озвучка в чате идёт через внутренний Silero агента (audio_url=null
по дизайну — чтобы не дублировать речь); если нужен скачиваемый аудиофайл в чате —
добавить маршрут `/api/chat/audio/<name>` (отдельная задача). 

Hermes = MVP плавная мышь + XToys + чат-хаб (WebUI/Camera/Context Feed), grounding в реальный код, гейты безопасности сохранены, от 2026-08-03

---

**Задача:** по TASK_hermes_verifier_applier.md добавить в существующий `uni/devcoord/` два модуля — `verifier.py` (проверка утверждений ИИ по реальному репозиторию) и `applier.py` (применение патча в ветке `review/<id>` + тесты, стоп перед коммитом). Одна задача = одно изменение.

**Изменённые файлы:**
| Файл | Что сделано |
|------|-------------|
| `uni/devcoord/models.py` | 🤖 добавлен `ClaimVerificationResult` + поле `verified: Optional[ClaimVerificationResult] = None` в `ProviderResult` (расширение, классы не переписаны) |
| `uni/devcoord/verifier.py` | 🤖 новый `Verifier.verify_claim(claim, file_hint)` — извлекает code-токены из утверждения и ищет их в реальных файлах (grep-подобно), поддержка отрицательных утверждений; `ClaimVerificationResult` определён в models.py, чтобы не было цикла импортов |
| `uni/devcoord/coordinator.py` | 🤖 опциональный параметр `verifier` в `__init__`; после ответа провайдера кладёт `result.verified = verifier.verify_claim(verify_claim)` (пробрасывается через `run_next`/`run_all`) |
| `uni/devcoord/applier.py` | 🤖 новый `Applier`: `apply_and_test` создаёт `review/<task_id>`, применяет патч, гонит `pytest -q` + `scripts/check_architecture.py --strict`, при падении — откат ветки (`reverted`), при успехе — `awaiting_human_confirmation`; **никогда не коммитит и не мержит**; `confirm_merge` вызывается только человеком |
| `tests/test_devcoord_verifier_applier.py` | 🤖 новые тесты: Verifier (true/false/negated/no-tokens на реальном репозитории), coordinator round-trip (сохраняет `verified` в store), Applier на scratch-git (pass→awaiting+never-commits, fail→reverted, unapplicable patch→reverted) |

**НЕ тронуто (по заданию):** `webui/index.html`, `script.js`, `style.css`, `scripts/dev_panel.py`, `devcoord/store.py`, `devcoord/providers.py`, `planner.py`/`planner_interface.py`. Не созданы `dispatch.py`/`cli.py`/`providers/openai_compat.py`.

**Отклонение от псевдокода задания (обосновано):** `ClaimVerificationResult` размещён в `models.py`, а не в `verifier.py` — иначе возникал бы цикл импортов (`verifier`→`models`, а `models.ProviderResult.verified` ссылался бы на `verifier`). Требование «одно поле `verified` в models.py» выполнено.

**Проверено:**
```
PYTHONPATH=/c/LLM/UNI /c/LLM/python312/python.exe -m pytest tests/test_devcoord_verifier_applier.py -q
→ 9 passed in 25.88s

PYTHONPATH=/c/LLM/UNI /c/LLM/python312/python.exe -m pytest tests/ -q
→ 119 passed, 7 subtests passed, 1 failed
   (единственный fail: tests/council/test_webui.py::test_frontend_roll_call_has_no_removed_notice_dependency
    — про фронтенд runRollCall, НЕ мой код, предсуществующий; devcoord не затронут)

/c/LLM/python312/python.exe scripts/check_architecture.py --strict
→ Summary: 1 error(s), 0 warning(s)
   ERROR: uni/capabilities/computer.py: capability imports another capability: uni.capabilities.uni_action_badge
   (предсуществующая ошибка архитектуры, НЕ в моих файлах; по заданию computer.py не трогать)
```

**Что должен сделать человек:** при реальном применении патча через `Applier.apply_and_test` ветка `review/<task_id>` остаётся до явного `confirm_merge()` — посмотреть diff и вывод тестов, затем подтвердить Merge вручную. `apply_and_test` не коммитит и не мержит сам.

Hermes = добавил devcoord/verifier.py + applier.py + поле verified, 9 новых тестов проходят; отчёт в .hermes/desktop-attachments/ от 03.08 отменяет необходимость править computer.py (вне scope) от 2026-08-03

---

### 2026-08-03 15:40 · Hermes · DevCoord MVP + Knowledge Base (расширение devcoord)

**Задача:** по TASK_hermes_devcoord_knowledge_base.md (Qwen3.8) адаптировать под
реальный код и реализовать Фазы 0–3: снять блокер check_architecture, Knowledge
Base, расширить Coordinator (select_participants + промпты), Aggregator
(score_response/aggregate_with_quality), Pipeline, CouncilBridge, CLI.

**Ключевое:** код Qwen в ТЗ был под ВЫМЫШЛЕННЫЙ API (Coordinator/DevTask,
ProviderResult.response/.provider/.confidence). Переписал под реальный
DevelopmentCoordinator / DevelopmentTask / ProviderResult.content/.provider_id.

**Изменённые/новые файлы:**
| Файл | Что сделано |
|------|-------------|
| `uni/action_badge.py` | 🤖 ПЕРЕНОС `uni/capabilities/uni_action_badge.py` сюда (вне папки capabilities) |
| `uni/capabilities/computer.py` | 🤖 правка импорта → `from uni.action_badge import UniActionBadge` |
| `uni/docs/AGENT_CURSOR.md` | 🤖 правка пути в доке |
| `uni/devcoord/models.py` | 🤖 поле `confidence: float = 0.5` в ProviderResult |
| `uni/knowledge/__init__.py` | 🤖 пустой init (пакет) |
| `uni/prompts/system_prompt_{advisor,critic,executor}.txt` | 🤖 ролевые промпты |
| `uni/devcoord/coordinator.py` | 🤖 select_participants(budget,max) + загрузка промптов + advisor в run_next; опц. kb/prompts_dir |
| `uni/devcoord/aggregator.py` | 🤖 aggregate + score_response + aggregate_with_quality |
| `uni/devcoord/pipeline.py` | 🤖 DevPipeline.process_task (real API) |
| `uni/devcoord/council_bridge.py` | 🤖 CouncilBridge (real DevelopmentTask) |
| `uni/knowledge/__main__.py` | 🤖 CLI list-skills/search/export-skills |
| `uni/devcoord/__main__.py` | 🤖 CLI confirm <id> [--repo] |
| `tests/test_knowledge_base.py` | 🤖 6 тестов |
| `tests/test_devcoord_pipeline.py` | 🤖 6 тестов (aggregator/select/pipeline/bridge) |

**НЕ тронуто (по жёстким рамкам):** webui/*, uni/council/*, scripts/dev_panel.py,
planner*. auto_dev_loop.py / critic_handler.py НЕ создавались (дублируют
pipeline/verifier — по указанию Qwen в Фазе 2.4).

**Проверено:**
```
scripts/check_architecture.py --strict  →  Summary: 0 error(s), 0 warning(s)
pytest tests/test_knowledge_base.py tests/test_devcoord_pipeline.py tests/test_devcoord_verifier_applier.py -q
  → 27 passed in 26.31s
python -m uni.knowledge list-skills     → (no skills yet)  [OK]
python -m uni.knowledge search "retry"  → (no matching responses)  [OK]
python -m uni.knowledge export-skills   → экспорт пустой KB  [OK]
Сквозной smoke (отдельный scratch git):
  Applier.apply_and_test("SMOKE", patch) → status="awaiting_human_confirmation", ветка review/SMOKE создана
  confirm_merge("SMOKE") (in-process + через CLI --repo) → merge-коммит в base, review-ветка сохранена
```

**Что должен сделать человек:** при реальном патче через Pipeline/Applier — ветка
`review/<id>` остаётся; посмотреть diff+тесты, затем `python -m uni.devcoord
confirm <id> [--repo .]` (только вручную). apply_and_test не коммитит/не мержит.

Hermes = DevCoord MVP+KB реализован и проверен (27 тестов, гейт 0 errors, smoke merge ок) от 2026-08-03

---

## 🗺️ Карта проекта (актуальная)

| Путь | Статус |
|------|--------|
| `uni/` | **КАНОН.** Единственная рабочая реализация. Правки только сюда. |
| `uni Hermes old/` | архив версии Hermes от 03.08. Только чтение. |
| `uni-test/`, `Telegram/`, `copilot-worktrees/` | справочные, не трогать |
| `.backup-before-merge/` | бэкап перед слиянием 03.08, можно удалить после приёмки |

Ключевые инварианты — в `AGENTS.md`. Архитектура — `ARCHITECTURE.md`.

**Команды проверки:**
```
cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m pytest -q
cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe scripts/check_architecture.py
```
**Запуск WebUI:**
```
cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m uni.webui --port 8787
```

---

## 🕓 Хронология

<!-- НОВЫЕ ЗАПИСИ ДОБАВЛЯТЬ СРАЗУ ПОД ЭТОЙ СТРОКОЙ -->

### 2026-08-03 05:40 · Hermes · Раздача статики в WebUI (исправление 404 после разделения index.html) 🤖 AI-правка

**Задача.** Пользователь разнёс `index.html` на 3 файла (`index.html` + `style.css` + `app.js`,
плюс темы `theme_*.css`). После этого интерфейс перестал грузиться: DevTools показывал
`404` на `http://127.0.0.1:8787/style.css` и `/app.js`. Гемини предложил Express/FastAPI —
неприменимо (сервер на stdlib `http.server` + кастомный `do_GET`).

**Причина (точная).** `uni/webui/server.py` в `do_GET` обрабатывал только `/` и `/api/*`;
любой другой путь падал в `self._send(404, ...)`. Раньше CSS/JS были внутри `index.html`
(отдавался как `/`), поэтому 404 не было. После разделения браузер стал запрашивать
`style.css`/`app.js` по отдельным URL → сервер не умел их отдавать.

**Что сделано (только `server.py`, без трогания CSS/HTML/JS):**
- Добавлена константа `_STATIC_TYPES` (белый список MIME: `.css/.js/.ico/.svg/.png/.json/.html/.woff2/.woff`).
- В `do_GET`, сразу после блока `/` и **перед** `/api/*`, добавлена ветка:
  если `parsed.path` не начинается с `/api/`, берём `suffix = Path(path).suffix.lower()`;
  если suffix в `_STATIC_TYPES` И файл существует внутри `_HERE` (через `is_relative_to`)
  → отдаём с правильным Content-Type.

**Критичное исправление по ходу (security):** первая версия правки отдавала ЛЮБОЙ файл
из папки webui (условие `is_file()` без фильтра по типу). Тест выявил, что
`/server.py` и `/../server.py` отдавали **исходник сервера** (200 + тело). Исправлено
на **белый список расширений**: `.py`/`.yaml`/`.txt`/`.bak` НЕ отдаются (404), даже
если лежат в папке. `urlparse` уже нормализует `..`, плюс `is_relative_to` страхует от
выхода за пределы `webui/`. Path traversal закрыт.

**Проверено (реальный вывод curl, сервер 8787):**
```text
/                     → 200 text/html
/style.css            → 200 text/css
/app.js               → 200 application/javascript
/theme_blueprint.css  → 200 text/css
/api/participants     → 200 application/json
/nope.txt             → 404
/server.py            → 404   (исходник НЕ отдаётся)
/../server.py         → 404   (path traversal закрыт)
/config.yaml          → 404
/../config.yaml       → 404
/app.js.bak           → 404
```
Браузерную проверку (Ctrl+F5) оставил за пользователем — сервер теперь отдаёт ассеты.

**Замечание.** Текущий `server.py` (527 строк) и `app.js` — версия пользователя (Гемини),
где фронтенд использует `/api/participants` (не `/api/status`). Эндпоинт `/api/status`
отсутствует в этой сборке — но `app.js` его и не запрашивает, поэтому 404 на `/api/status`
не ломает UI. Восстановление `/api/status` (если понадобится для v2.7-фронтенда) — отдельная задача.

Hermes = раздача статики в WebUI + закрытие path traversal от 03.08.2026

---
### 2026-08-03 04:56 · Hermes · Реализация UNI-UI-002 (адаптация ТЗ под реальный стек)

**Задача.** Пользователь сказал СТОП: при адаптации v2.7 я заплодил фоновые серверы WebUI
на портах 8790/8792/8793/8794/8796 (проверка JS), а у пользователя был свой сервер на 8787.
Нужно убрать дубли и привести к одному серверу.

**Что сделано:**
1. Убиты все мои фоновые серверы WebUI (8790–8796) через `taskkill /F /PID`.
2. `uni/webui/index.html` заменён на v2.6 из `.backup-before-merge/index.html`
   (md5 совпал: `5b6ee052fe90216b7cdac4bf06c9328e`).
3. `tests/council/test_webui.py` возвращён на проверку `runRollCall` (соответствует v2.6;
   ранее был переключён на `runCheckIn` под v2.7).
4. Запущен ОДИН сервер строго на 8787: `C:/LLM/python312/python.exe -m uni.webui --port 8787`.
5. Создан отдельный лог сессии `UNI_SESSION_LOG_2026-08-03.md`.

**Проверено:**
```text
netstat 87xx LISTENING      → только 8787
curl http://127.0.0.1:8787/ → HTTP 200
curl /api/status            → participants[] (11 участников)
pytest -q                   → 111 passed, 7 subtests passed
```

Hermes = остановка лишних серверов и возврат к v2.6 от 03.08.2026

---
### 2026-08-03 04:56 · Hermes · Реализация UNI-UI-002 (адаптация ТЗ под реальный стек)

🤖 AI-правка

**Задача.** ТЗ `UNI-UI-002` (v2.8.0-draft) описывало React/Tailwind-стек (`src/`, `tailwind.config.js`,
`uni/cdp_controller.py`), которого в каноне `C:\LLM\UNI` НЕТ (фронтенд — один vanilla `uni/webui/index.html`).
По согласованию с координатором ТЗ адаптировано под реальный стек: все 5 фич реализованы в
`uni/webui/index.html` (как «аналог v2.7» из самого ТЗ) + `uni/browser_session.py` + расширение `server.py`
(вызов детектора лимитов и поля в `/api/status`).

**Изменённые файлы (канон):**
- `uni/browser_session.py` — `check_limit_banner(page)` (try/except + asyncio.wait_for ≤2с; регэкспы из ТЗ:
  «…час…минут до сброса лимита», «rate limit», «supergrok», «превышен лимит»). Возвращает
  `{limit_exceeded, reset_in:"16ч 11мин"}`. Ядро CDP не тронуто.
- `uni/webui/server.py` — `_LIMIT_CACHE` (module-level), `_detect_limits(session, selected)` вызывается перед
  `round_.run` для browser-участников через `session.page_for_host(host)`; поля `limit_exceeded`/`limit_reset`
  добавлены в `_participant_statuses` и в payload `/api/status` (v2.7-формат).
- `uni/webui/index.html` (vanilla) — 5 фич:
  1. Чекбоксы выбора в левой панели `УЧАСТНИКИ` (синхронизация с `state[a.name].on`, счётчик «X/11 АКТИВНЫ»,
     default checked по CDP+tab+ready; ChatGPT/Codex unchecked как unavailable).
  2. Grid-карточки ответов (уже были) + бейджи CDP/Вкладка/state в poll.
  3. Реакция на лимит: плашка `Лимит: ~…` + класс `.limited`, авто-снятие чекбокса при `limit_exceeded`.
  4. Кнопка «🧩 Синтезировать решение» (вкладка «Итог»): активируется после раунда, шлёт промпт-синтез
     к Hermes через `/api/round/start` (only:["Hermes"], system_prompt из ТЗ).
  5. Вкладка «Журнал»: таблица аналитики (Имя/Транспорт/Время/Символы/Лимит/Результат) + экспорт `[ JSON ]`/`[ Markdown ]`.

**Проверено (живьём, сервер 8787, браузер):**
- 0 JS-ошибок в консоли (F12).
- 11 чекбоксов, default 10 checked, ChatGPT unchecked; снятие чекбокса → счётчик «9/11 активны».
- Индикатор агента: idle→running («Думает…») при раунде, обратно idle.
- Реальный раунд (Только API): 10 карточек, таблица аналитики заполнилась (Gemini/Groq/OpenRouter/HuggingFace/Hermes
  с транспортом, временем, символами, лимитом OK, результатом).
- Кнопка «Синтезировать» активируется после раунда; запрос уходит к Hermes (Hermes медленный — ответ >60с,
  но логика парсера `participant_done` корректна, проверено curl: SSE шлёт init/start/participant_start).
- Экспорт JSON/MD: кнопки кликабельны, `renderAnalytics()` рендерит таблицу без ошибок.
- `/api/status` отдаёт `limit_exceeded`/`limit_reset` (проверено curl).
- `pytest` → 111 passed, 7 subtests.

**Отклонения от ТЗ (фиксирую):**
- Нет `src/`, Tailwind, `uni/cdp_controller.py` — фичи в vanilla `index.html` + `browser_session.py` (разрешено самим ТЗ: «public/index.html (или аналоги v2.7)»).
- Детектор лимитов вызывается из `server.py` (WebUI-сервер, не ядро planner/router) — иначе UI не может
  читать чужую вкладку (CORS). Это расширение статуса, не «ядро UNI» (запрет ТЗ сохранён).
- Лимит-детектор НЕ тестировался на живом Grok (нет открытой вкладки Grok с баннером) — регэкспы и try/except проверены статически.

Hermes = реализация UNI-UI-002 (адаптация под vanilla-стек) от 03.08.2026

---
### 2026-08-03 04:10 · Hermes · Сводный отчёт по пакету задач (Fallback · Артефакты · Keep-Alive · Статусы v2.7)

🤖 AI-правка

**Задача.** Выполнить итоговый пакет ТЗ (сводный план DeepSeek + Gemini + журнал):
отказоустойчивость провайдеров, резервирование артефактов, персистентность/keep-alive
браузерной сессии CDP, компактный WebUI v2.7 с фоновым детектором статусов.

**Изменённые файлы (канон `uni/`):**

1. `uni/council/provider.py` — `FallbackProvider(CouncilProvider)` + расширение
   `build_provider()` каскадным перебором `fallbacks`. Контракт `ParticipantReply`
   не менялся → `round.py`/`run.py` нетронуты. Считается провалом `error` или пустой
   текст (ловит 403/404/DNS/timeout). При тотальном сбое — агрегированная ошибка.
2. `uni/council/participants.py` — `_fallback_chain()` читает
   `council.fallbacks.{endpoint}: [имена]` из config; бэкапы строятся с `resolve_endpoint`,
   api-ключи из `fallbacks` НЕ попадают в публичный `spec` (только `_fallbacks` = список имён).
3. `uni/config.py` — поле `CouncilConfig.fallbacks: dict` (по умолчанию `{}`, поведение
   прежнее для тех, кто не настроил).
4. `uni/devcoord/artifacts.py` — `save_artifact_with_backup(path, content)` копирует
   существующий файл в `<name>_YYYYMMDD_HHMMSS.bak` (через `copy2`), разводит коллизии
   в ту же секунду, пишет в лог, создаёт папки.
5. `uni/browser_session.py` — `start_keep_alive(30с)` пинг `page.evaluate("1+1")`;
   `stop_keep_alive()`; `close()` для CDP-режима делает `browser.close()` (== disconnect,
   НЕ убивает браузер пользователя); `ensure_alive()` для CDP переподключается к тому же
   `cdp_url` вместо запуска второго браузера.
6. `uni/webui/server.py` — `/api/status` переписан под v2.7:
   `{participants:[{name,type,cdp_ok,tab_found,state}], agent:{...}}` (из `_participant_statuses`);
   воркер раунда обновляет `_AGENT_STATUS` (idle/running/error).
7. `tests/council/test_webui.py` — `test_frontend_roll_call_has_no_removed_notice_dependency`
   обновлён под v2.7 (проверяет `runCheckIn` вместо устаревшего `runRollCall`).

**НЕ тронуто (намеренно):** `uni/webui/index.html` — пользователь заменил его на v2.7
до постановки задачи; мои правки v2.6 (режимы переклички, кнопки копирования, ссылка на
отчёт, плашка `statusWidget`) не перенеслись. Живая копия v2.6: `.backup-before-merge/index.html`.
Из моего слияния в v2.7 уцелели только бэкенд-части: `_tcp_open/_dns_ok`, `/api/report/raw`,
`model` из config, теперь `/api/status` v2.7.

**Проверено (реальный вывод команд):**

```text
pytest -q                              → 111 passed, 7 subtests passed   ✅
pytest tests/council tests/devcoord    → 30 passed in 4.16s             ✅
импорт 6 изменённых модулей            → OK                             ✅
check_architecture.py                  → 1 error (предсуществующий)
```

- **Fallback** (живой прогон): `openrouter(403)→gemini(404)→groq(ok)` вернул ответ groq;
  все упали → `all providers failed — or: 403; gm: 404`; первый живой → бэкапы не дёрнуты;
  пустой текст → следующий; без `fallbacks` → `ApiProvider` (поведение прежнее).
  В `load_participants(only=['OpenRouter'])` при `council.fallbacks.openrouter=[groq,hermes]`
  строится `FallbackProvider` с шагами `['openrouter','groq','hermes']`; ключ не утёк в `spec`.
  `config.yaml` после теста восстановлен (md5 совпадает).
- **Артефакты** (живой прогон в /tmp): создание + 2 бэкапа с разведением суффикса `_1`;
  содержимое v1/v2 сохранено, итог v3; лог `Artifact backup created`.
- **Keep-Alive/Reconnect** (живьём на CDP 127.0.0.1:9222): подключение `owns_context=False`;
  пинг жив; повторный `start_keep_alive` не дублирует задачу; симуляция разрыва →
  `ensure_alive()` переподключился (6 вкладок); `close()` → браузер пользователя остался
  жив (curl 9222 вернул 6 страниц).
- **Статусы v2.7** (живьём, порт 8794): `/api/status` вернул 11 участников, у 4
  (DeepSeek/QWEN/Qwen Coder/Claude) `cdp_ok:true/tab_found:true`, у остальных `Off/Нет`;
  панель участников отрисовала 11 карточек, 0 JS-ошибок; «🔔 Перекличка» автозаполнила
  тему и бриф по шаблону; чип «🛡️ Политика безопасности» открыл `securityModal`.

**Ошибка архитектуры** `uni/capabilities/computer.py: capability imports another capability
uni.capabilities.uni_action_badge` — ПРЕДСУЩЕСТВУЮЩАЯ (версия Grok, не моя правка).
Вне рамок ТЗ; не исправлял, чтобы не ломать чужой модуль. Нужен отдельный ADR/задача.

Hermes = реализация пакета задач (Fallback, Артефакты, Keep-Alive CDP, Статусы v2.7) от 03.08.2026

---

### 2026-08-03 03:30 · Hermes · Реализация компактного WebUI v2.7 и детектора статусов

🤖 AI-правка

**Контекст.** `uni/webui/index.html` был заменён пользователем на компактную сборку
v2.7 (Inter, amber/green/red, крупные вкладки, левая панель участников, авто-заполнение
переклички, кликабельный чип политики). Новый фронтенд ждёт от `/api/status` формат
`{participants:[{name,type,cdp_ok,tab_found,state}], agent:{...}}` и auto-poll раз в 2.5с.
Ранее мой `/api/status` отдавал только `{state,last_action,round_id,updated}` → фронт
падал при `data.participants.forEach`.

**Что сделано (только `server.py` + `tests/council/test_webui.py`):**
- `/api/status` переписан на двухуровневый формат: `participants[]` (из
  `_participant_statuses`, маппинг `transport→type`, `status=='ready' and browser→cdp_ok/tab_found`)
  и `agent` (прежний `_AGENT_STATUS`, обновляется воркером раунда).
- Тест `test_frontend_roll_call_has_no_removed_notice_dependency` обновлён под v2.7:
  вместо устаревшего `runRollCall` проверяет наличие `runCheckIn` (авто-заполнение переклички).

**Проверено (живьём, порт 8794):**
```
$ curl /api/status | python
ключи верхн. уровня: ['participants', 'agent']
участников: 11
пример[0]: {"name":"DeepSeek","type":"browser","cdp_ok":true,"tab_found":true,"state":"ready",...}
```
- Браузер: панель участников рисует 11 карточек, у 4 (DeepSeek/QWEN/Qwen Coder/Claude)
  `CDP: OK / Вкладка: Найдена`, у остальных `CDP: Off / Вкладка: Нет`. JS-ошибок: 0.
- Кнопка «🔔 Перекличка» автозаполняет тему `Проверка доступности участников` и бриф
  по шаблону `[Имя_ИИ]: подключён, готов к работе.` — по ТЗ п.3.
- Чип «🛡️ Политика безопасности» кликабелен → открывает `securityModal` (ТЗ п.4).
- Крупные вкладки `💬 Текущий раунд / 📝 Итог / 📜 Журнал работ` присутствуют (ТЗ п.2).

**Команды проверки (реальный вывод):**
```
pytest -q     → 111 passed, 7 subtests passed   ✅
check_architecture.py → 1 error (uni\capabilities\computer.py: capability imports
                       another capability: uni.capabilities.uni_action_badge)
```
Ошибка архитектуры — ПРЕДСУЩЕСТВУЮЩАЯ, в `computer.py` (версия Grok, не моя правка).
Не исправлял: выходит за рамки ТЗ и ломает чужой модуль. Требует отдельного ADR/задачи.

**Важное замечание для других ИИ.** Мои правки v2.6 (режимы переклички API/Браузер/Все,
модалка «некого опрашивать», popover политики, кнопки копирования журнала, ссылка на
отчёт, плашка статуса `statusWidget`) НЕ перенеслись в v2.7 — файл `index.html` был
полностью заменён. Из моего слияния в v2.7 живы только бэкенд-части: честные статусы
`_tcp_open/_dns_ok` и `/api/report/raw` (в `server.py`), `model` из config (в
`council/_keys.py`+`participants.py`), и теперь `/api/status` v2.7. Исходная копия v2.6
сохранена в `.backup-before-merge/index.html`.

**Решение пользователя:** реализовать по ТЗ v2.7 (фронтенд уже был на диске).

Hermes = реализация компактного WebUI v2.7 и детектора статусов от 03.08.2026

---

### 2026-08-03 03:10 · Hermes · Сверка внешнего ТЗ (8 пунктов) с репозиторием — БЕЗ правок кода

🤖 AI-правка (только этот журнал; исходники не менялись)

**Задача.** Пользователю передали план из 8 пунктов (HuggingFace, курсор, fallback,
confidence, персистентная сессия, YAML-конфиг, dual cursor, версионирование артефактов).
Перед реализацией сверил план с фактическим кодом.

**Результат сверки:**

| П. | Задача из плана | Факт в репозитории |
|----|-----------------|--------------------|
| 1 | HuggingFace провайдер | ✅ **уже есть** — `council/participants.py` + `config.yaml`, `router.huggingface.co/v1`, в раунде 004945 отвечал OK |
| 2 | Плавный курсор «Мышка Юни» | ✅ **уже есть** — `uni/agent_cursor.py` (Grok), подпись UNI, `move_ms: 220` |
| 6 | Единая схема YAML | ✅ **уже есть** — `config.yaml` + Pydantic-модели в `uni/config.py` |
| 7 | Dual cursor / панель статуса | 🟡 наполовину — курсор есть, панели статуса в углу страницы нет |
| 3 | Fallback провайдеров | ❌ нет ни в `devcoord/coordinator.py`, ни в `council/provider.py` |
| 4 | Confidence + матрица консенсуса | ❌ нет, слово `consensus` только в докстрингах |
| 5 | Персистентная браузерная сессия | ⚠️ не доисследовано, возможно частично закрыто через CDP |
| 8 | Версионирование артефактов | ❌ нет — ни `.bak`, ни `CHANGELOG` в `devcoord/artifacts.py` |

**Три расхождения плана с кодом (важно для всех ИИ):**

1. **План адресует не тот модуль.** Пункты 1, 2, 7 предлагают править
   `uni/devcoord/providers.py`, но консилиум живёт в **`uni/council/`**. Это разные
   подсистемы: `devcoord` — координация задач разработки, `council` — совет моделей.
   Курсор вообще в `uni/agent_cursor.py`. Реализация «по букве плана» создаст дубли.
2. **Пункт 1 — регресс.** План предлагает старый Inference API
   `router.huggingface.co/hf-inference/models/{model_id}` с сырыми ответами и
   `503 Model Loading`. Сейчас стоит OpenAI-совместимый `/v1`, который **уже работает**.
3. **Пункт 4 требует ADR.** Смена формата ответа участника на
   `{"answer", "confidence", "reasoning"}` меняет публичный контракт совета.
   По `AGENTS.md` такое нельзя менять без принятого ADR.

**Полезный остаток плана:** п.3 (fallback), п.8 (версионирование артефактов),
панель статуса из п.7. Наиболее ценный — **п.3**: сейчас OpenRouter 403 и Gemini 404
роняют участника вместо переключения на живого.

**Проверено (команды-разведка, только чтение):**
```
grep huggingface uni/devcoord/providers.py uni/council/participants.py → HF только в council
ls uni/agent_cursor.py                                                 → есть, 7450 байт
grep "fallback|for provider in" devcoord/coordinator.py council/provider.py → пусто
grep "confidence|consensus" uni/council/*.py                           → только докстринги
grep "\.bak|CHANGELOG" uni/devcoord/artifacts.py                       → пусто
```

**Решение пользователя:** код не трогать, сверку отдать другому ИИ на согласование.

**Что должен сделать человек:** передать эту таблицу автору плана, чтобы он
переадресовал пункты 1/2/7 в правильные модули и снял уже выполненное.

Hermes = сверка внешнего ТЗ с репозиторием от 03.08.2026

---

### 2026-08-03 02:30 · Hermes · Слияние правок Hermes в версию Grok

🤖 AI-правка

**Задача.** Пользователь закачал версию Grok в `uni/` — у неё заработал браузерный
транспорт. Прежняя версия Hermes уехала в `uni Hermes old/`. Нужно перенести в канон
полезное из версии Hermes, не сломав достижения Grok.

**Что было у Grok лучше (сохранено без изменений):**
- `uni/agent_cursor.py` + хуки в `uni/browser_session.py` — видимый курсор агента
  в браузере. Вероятная причина, почему браузерные участники «наконец заработали».
- Полный редизайн `index.html`: Space Grotesk / Inter / JetBrains Mono,
  тёплая графитовая палитра, янтарный акцент.
- Корректные ключи в `config.yaml` (у Hermes ключ Gemini был склеен из трёх копий).

**Найденный баг в версии Grok:** в `config.yaml` прописаны `model:`, но код их
не читал — `_keys.py` возвращал только `base_url` + `api_key`. Реально уходили
модели из реестра `participants.py`:

```
config говорит  openrouter → deepseek/deepseek-chat-v3.1:free
код слал        deepseek/deepseek-chat        (403 Forbidden)
config говорит  hermes → qwen3.5-9b
код слал        local
```

**Изменённые файлы:**

| Файл | Что сделано |
|------|-------------|
| `uni/council/_keys.py` | `resolve_endpoint` отдаёт `model` из config |
| `uni/council/participants.py` | `model` из config переопределяет реестр |
| `uni/webui/server.py` | `_tcp_open` / `_dns_ok` — честные статусы API; `/api/report/raw`; заглушка `/favicon.ico`; `/api/report` отдаёт `path` + `raw_url` |
| `uni/webui/index.html` | режимы переклички API/Браузер/Все; модалка «некого опрашивать»; popover политики; кнопки копирования журнала и отдельной строки; кликабельная ссылка на файл отчёта; poll статусов раз в 4 с |

**Проверено:**
```
model из config применяется  → OpenRouter=deepseek-chat-v3.1:free, Hermes=qwen3.5-9b
_participant_statuses        → Hermes: ready (локальный сервер отвечает 127.0.0.1:1234)
                               DeepSeek/QWEN/Qwen Coder/Claude/Grok: ready (вкладки найдены)
```

**Инфраструктура на машине пользователя (замер 03.08):**
- CDP `127.0.0.1:9222` жив (YaBrowser), 5 браузерных участников `ready`
- LM Studio на `127.0.0.1:1234`, модель `qwen3.5-9b`
- `browser_enabled: true`, `free_tier_only: true`, профиль `.uni-council-browser-profile`

**Живые probe-запросы к API (важно для всех ИИ):**
```
Hermes  qwen3.5-9b                 OK 200
Groq    llama-3.3-70b-versatile    рабочий
OpenRouter deepseek/deepseek-chat        403 Forbidden  (лимит ключа)
OpenRouter deepseek-chat-v3.1:free       404 Not Found  (такого id нет)
Gemini  gemini-1.5-flash                 404 Not Found  (снята с v1beta)
```

**Что должен сделать человек:**
1. **OpenRouter** — выпустить новый ключ; подобрать существующий `:free`-id
   (текущий в конфиге даёт 404).
2. **Gemini** — `gemini-1.5-flash` снята; заменить на актуальную модель.
3. **LM Studio** держать запущенным на 1234, иначе Hermes станет `unavailable`.
4. **ChatGPT/Codex** — вне scope, нужен `codex` в PATH.

Hermes = слияние правок Hermes в канон Grok от 03.08.2026

---

## ❓ Открытые вопросы

- [ ] Внешнее ТЗ из 8 пунктов: 1/2/6 уже выполнены, 1 — регресс, 4 — нужен ADR.
      Ждём переработанную версию плана от автора.
- [ ] п.5 плана (персистентная браузерная сессия) — не доисследован, нужен разбор
      `uni/browser_session.py` на предмет keep-alive.
- [ ] `uni/webui/index.html` не отслеживается git (`??`) — добавить в индекс?
- [ ] Актуальный `:free`-id для OpenRouter не подобран (текущий даёт 404).
- [ ] Актуальная модель Gemini не подобрана (`gemini-1.5-flash` → 404).
- [ ] Кнопка «Открыть вкладки участников» через CDP — нужен новый backend-эндпоинт,
      отдельная задача.
- [ ] `.backup-before-merge/` удалить после приёмки слияния.

---

## ✍️ Накопленные подписи

```
Hermes = слияние правок Hermes в канон Grok от 03.08.2026
Hermes = сверка внешнего ТЗ с репозиторием от 03.08.2026
```
