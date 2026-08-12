# Аудит кода UNI (canonical `uni/`) — план улучшений без внесения изменений

**Дата:** 2026-07-31 · **Статус:** только аудит и план, правки не вносились.
**Охват:** всё ядро оркестрации и все capability, прочитанные с диска (`uni/`).
**Контекст:** структура уже нормализована (единый git-корень `C:\LLM\UNI`, `uni/` — canonical), тесты проходят (69 passed / 3 subtests). Цель этого документа — найти недостатки и предложить план «постепенного укрепления» работающего Fast-track, как рекомендовал предыдущий ревью.

---

## 1. Критические / высокие недостатки

### 1.1 `get_tool_schemas` рассинхронизирован с `ToolExecutor._ROUTING`
`uni/tools/definitions.py` описывает только **12 инструментов** (xtoys/browser/vision),
в то время как `uni/tools/executors.py::_ROUTING` знает **56** (включая `computer.*`,
`camera.*`, `speech.*`). В `_free_form` (event_loop.py:821) LLM получает только эти 12
схем. Следствие: в свободном диалоге модель не может вызвать `computer.*`,
`camera.*`, `speech.listen` и т.д. — они недоступны хотя бы на уровне сchemas, хотя
маршрутизация для них есть.

**План:** сгенерировать schemas автоматически из `_ROUTING` + декларативных
описаний в каждом capability (`Capability.get_tools()` уже есть, но возвращает `[]`
везде). Заполнить `get_tools()` в каждом capability и собирать schemas из реестра,
а не дублировать вручную в `definitions.py`.

### 1.2 `parse_direct_command` — хрупкая if-цепочка с дублями
`event_loop.py:85-256` — ~170 строк вложенных `if/elif` на regex. Повторяющиеся
проверки `mentions_xtoys and any(word in lowered ...)`. Любое новое правило требует
ручного встраивания и легко ломает порядок (например, «интенсивность» матчится раньше
«выключи игрушку», хотя «выключи игрушку» должен быть приоритетнее).

**План:** заменить цепочку на таблицу правил `(priority, regex, factory)` или на
небольшой парсер с приоритетами. Каждое правило — отдельная функция. Это уберёт
дубли и сделает порядок явным.

### 1.3 Глобальные блокировки инструментов (`_tool_lock`, `_audio_lock`)
`event_loop.py:67-68` один `asyncio.Lock()` на все инструменты и один на audio.
Следствие: пока идёт `browser.navigate` (Playwright I/O), заблокирован `speech.listen`
и `camera.snapshot`. В интерактивном режиме это вызывает «глухие» паузы: UNI «слушает»
только когда не занят браузером, хотя они не конфликтуют по ресурсам.

**План:** разделить локи по доменам (`_browser_lock`, `_vision_lock`, `_audio_lock`,
`_computer_lock`) или вообще убрать глобальный `_tool_lock`, оставив его только там,
где реально нужна сериализация (например, `VisualUIOperator` уже сам берёт `_tool_lock`).

### 1.4 `BrowserSession.ensure_alive` — опора на private API и гонка
`browser_session.py:73-83` проверяет `self._context._close_was_called`
(**приватный** атрибут Playwright) и вызывает `await self.start()` без удержания
`_lock` внутри `ensure_alive` (блокировка есть только в `start`, но между проверкой
и вызовом `start` из разных тасков возможна гонка).

**План:** не полагаться на `_close_was_called`; использовать `try/except` при
`active_page`/`goto` и пересоздавать контекст в `except`. Обернуть всю логику
восстановления в `async with self._lock:`.

### 1.5 Потеря результата LLM в `_free_form`
`event_loop.py:840-846`: если `final.error` или `final.text` пуст — возвращается
`compact` (сырые строки инструментов), а не сообщение об ошибке. Если `response.tool_calls`
есть, но `brain.chat` для финализации упал — пользователь получает «мусорный» вывод.

**План:** при `final.error` возвращать вежливое сообщение + лог; при пустом `final.text`
фолбэчить на `compact` только если он непустой, иначе — сообщение «не удалось
сформировать ответ».

---

## 2. Средние недостатки

### 2.1 `VisionCapability.save_dir` — относительный путь
`vision.py:102` `self.save_dir = Path("screenshots")` зависит от CWD. Если UNI
запущен не из `C:\LLM\UNI`, скриншоты падают не туда (и могут писаться в чужую папку).

**План:** сделать `save_dir` абсолютным (рядом с `session_logger.session_dir` или
через `config.logging.directory`).

### 2.2 `WorkingMemory.set` персистит на каждый вызов
`working_memory.py:117-128` вызывает `self.persist()` при каждом `set`. Для
интенсивного диалога это синхронная запись JSON на диск на каждый факт/обмен.

**План:** дебаунс-запись (таймер/счётчик) или писать только при `append_exchange` и
явном `set`, а не на каждый. Можно batch через `asyncio` task.

### 2.3 `_watch_screen_loop` — нагрузка и уязвимый хеш
`event_loop.py:698-729`: каждые 15с делает `save_screenshot` + `vision.analyze_screen`
(VLM). Без `imagehash` `_screenshot_hash` падает до размера файла (`event_loop.py:667`)
— два разных кадра с одинаковым размером будут пропущены, а разные — проанализированы
вхолостую. Кроме того, `vision.analyze_screen` каждые 15с в фоне — нагрузка GPU/CPU.

**План:** сделать `imagehash` обязательной зависимостью (или порог похожести по
среднему цвету), увеличить интервал по умолчанию до 20-30с, и при отсутствии
`imagehash` не анализировать вообще (выключать фичу).

### 2.4 `ToolExecutor.canonical_name` односторонний
`executors.py:62-64` `_API_ALIASES` мапит `xtoys_open → xtoys.open`, но обратно
нет. Если LLM вернёт `xtoys_open` (из schemas `definitions.py`), `execute` получит
`xtoys_open`, `canonical_name` вернёт `xtoys.open` — ок. Но если кто-то вызовет
`execute("xtoys.open")` напрямую — canonical = `xtoys.open` (совпадает). Проблема
только в рассинхроне имён (см. 1.1).

**План:** после 1.1 схемы будут использовать канонические имена `xtoys.open`, alias
оставить только для обратной совместимости.

### 2.5 `CameraCapability.start` — `notice_ack` не проверяется внешне
`camera.py:65` требует `notice_ack=True`, но `_camera_watch_worker` (event_loop.py:569)
вызывает `camera.snapshot` БЕЗ проверки, что `start` реально произошёл. Если `start`
упал (нет камеры), `snapshot` упадёт с «Камера не включена» — ок, но `_camera_look`
(event_loop.py:506) вызывает `camera.start` и сразу `camera.snapshot` — если `start`
вернул `success=False`, `snapshot` всё равно идёт.

**План:** в `event_loop` проверять `started.success` перед `snapshot` (частично уже
есть в `_camera_look`, но не в worker). Унифицировать через хелпер.

### 2.6 `visual_ui_operator.py` — мёртвый дублирующий код
`uni/visual_ui_operator.py` дублирует логику `computer.py` (VisualUIOperator vs
ComputerCapability). По предыдущему ревью — `planner.py`/`planner_interface.py`
оставлены как legacy; `visual_ui_operator` тоже стоит пометить legacy или удалить,
т.к. `EventLoop` использует его, но он дублирует `computer`.

**План:** либо перенести логику `VisualUIOperator` в `ComputerCapability` и вызывать
его, либо пометить `visual_ui_operator` как legacy и не трогать до реализации Planner.

---

## 3. Низкие / гигиена

### 3.1 `config.py` — секрет-редактирование не ловит XToys-токены
`WorkingMemory._SECRET_PATTERNS` и `SessionLogger._SECRET_PATTERNS` ловят
`пароль`/`api_key`/`token`, но не `XToys device token` или `authorization` в
нестандартном виде. По политике безопасности XToys это критично — но устройство
никогда не активируется программно, так что риск низкий. Всё же стоит добавить
`xtoys` в паттерны.

### 3.2 `EventLoop.__init__` — `memory.recent_messages` вызывается как callable
`event_loop.py:64-65`: `getattr(memory, "recent_messages", None)` затем `recent_messages(8)`
если callable. Но `recent_messages` — метод, он всегда callable. Если `memory` не
имеет этого метода — `None`, и `recent_messages(8)` не вызывается (ок). Но если
`memory` — это `WorkingMemory`, метод есть, и вызов `recent_messages(8)` работает.
Хрупко, но функционально.

### 3.3 `ScreenWatcher` наблюдения не экспонируются
`_screen_observations` (event_loop.py:79) — временный список, недоступный извне.
По ревью «временное Observation, не memory» — ок, но стоит добавить метод
`get_last_observation()` для отладки/логирования.

### 3.4 Тесты — пробелы покрытия
- Нет тестов на `event_loop._free_form` (LLM path), `ToolExecutor` routing,
  `browser_session.ensure_alive` гонку, `vision` JSON-parsing, `computer` (Windows-only,
  понятно), `camera` (нет устройства).
- `tests/fasttrack/test_xtoys_dom.py` — вероятно требует браузера (не запускался в CI).
- Нет теста на `parse_direct_command` приоритеты (например, «выключи игрушку» vs
  «интенсивность 0»).

**План:** добавить unit-тесты на `parse_direct_command` (матрица фраз),
`ToolExecutor` (мок-реестр), `BrowserSession._sanitize_url` (уже есть в integration),
`get_tool_schemas` (покрытие всех `_ROUTING`).

---

## 4. План по приоритетам (поэтапно, как рекомендовал ревью)

**Этап A — исправление рассинхрона инструментов (высокий):**
1. Заполнить `Capability.get_tools()` во всех capability.
2. Генерировать `get_tool_schemas` из реестра (удалить ручной `definitions.py`).
3. Проверить, что `_free_form` передаёт полный набор schemas.

**Этап B — надёжность оркестрации (высокий):**
4. Рефактор `parse_direct_command` в таблицу правил с приоритетами.
5. Разделить блокировки по доменам (`_tool_lock` → доменные локи).
6. Починить `ensure_alive` (без private API, с локом).
7. Починить обработку ошибок в `_free_form`.

**Этап C — производительность и гигиена (средний):**
8. `VisionCapability.save_dir` → абсолютный путь.
9. Дебаунс `WorkingMemory.persist`.
10. Усилить `_watch_screen_loop` (imagehash обязателен, интервал 20-30с).
11. Унифицировать camera start/snapshot проверки.
12. Пометить/удалить `visual_ui_operator` дубликат.

**Этап D — тесты и безопасность (низкий/средний):**
13. Добавить тесты на `parse_direct_command`, `ToolExecutor`, `get_tool_schemas`.
14. Расширить `SECRET_PATTERNS` на `xtoys`.

---

## 5. Что НЕ трогать (по политике безопасности)
- `XToysCapability` safety-гейты (`max_intensity`, `verified_physical: False`,
  `notice_ack` для камеры) — сохранить как есть.
- `agent.py` передачу `speech._session_logger` — ок.
- Структуру git (уже нормализована).

---

**Следующий шаг:** после утверждения плана (и совета с другим ИИ, если нужно) —
реализовать Этап A, затем B, с тестами после каждого. Никаких правок до утверждения
не вносилось.
