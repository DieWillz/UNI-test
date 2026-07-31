# Дизайн: консолидация `UNI` + новые возможности

> Статус: **ПРОЕКТ (не реализовано).** Код на диске не менялся. Файл — для обсуждения с другим ИИ.
> Дата: 2026-07-31. Автор обзора: Hermes.

## 0. Исходная ситуация (факты с диска)

- `C:\LLM\UNI` содержит **3137 файлов** (по `find`). Реально рабочий код — в `uni/` (отдельный git-репозиторий, `uni/.git`).
- Внутри `uni/` есть вложенный мусор: `uni/backup/uni/uni` (дубль дубля), `uni/Claude/uni`, `uni/TEAM_COORDINATION.md`.
- Корень `C:\LLM\UNI` забит копиями вариантов: `Uni-Claude/`, `Uni-DeepSeek/`, `Uni-OpenCode/`, `Claude/`, `backup/`, плюс устаревшие `capabilities/`, `tools/`, `roles/`, `config.py`, `uni.py`, `test_build*.py`, `test_planner_basic.py` — всё это дублирует/конфликтует с `uni/`.
- Огромные кэши: `.uni-browser-profile/` (Chromium: 245+174+50 файлов кэша), `ru_RU-irina-medium.onnx` (63 МБ, голос — **сохранить**).
- Рабочие unit-тесты: `tests/fasttrack/` (15 тестов `.py` + `__pycache__`). Не сломаны, **сохранить**.
- `tests/integration/test_conversation.py` — **сломан** (импортирует удалённый `CycleResult`) → удалить.

## 1. Цель

1. Свести всё рабочее в **одну папку** (`uni/`), без вложенных `uni/uni` и без дублей на верхнем уровне.
2. Реально удалить мусор (~4.2k→ останется ~150 файлов), не трогая рабочий код, голос, тесты, доки.
3. Добавить (дизайн ниже):
   - **A. Запуск приложений с откатом на «мышь + компьютерное зрение»** (если `xtoys.open`/launch не удалось — найти икону на экране, кликнуть, дождаться).
   - **B. Фоновый цикл скриншотов** каждые 15–20с, VLM-описание в память, чтобы UNI «всегда знала» что на экране.
   - **C. Правка TTS-бага** (эмодзи/спецсимволы ломают Piper → `KeyError: '😈'`).

---

## 2. План консолидации (что удаляем / что оставляем)

### 2.1 Удалить (мусор / дубли / кэши)
| Путь | Почему |
|---|---|
| `Uni-Claude/`, `Uni-DeepSeek/`, `Uni-OpenCode/`, `Claude/` | reference-варианты (по ADR-0001 канон — `uni/`); в корне не нужны |
| `backup/` (корневой, 275 файлов) | содержит `backup/1/uni/uni/...` — дубль дубля |
| `uni/backup/`, `uni/Claude/` | вложенные дубли внутри рабочего репо |
| `*.py:Zone.Identifier`, `*.txt:Zone.Identifier` и т.п. | Windows Mark-of-the-Web, не код |
| `__pycache__/` (везде) | скомпилированный мусор |
| `.uni-browser-profile/` | кэш Chromium (пересоздаётся) |
| `capabilities/`, `tools/`, `roles/` (корневые) | дубли `uni/capabilities` и т.д. |
| `config.py` (корневой), `uni.py`, `test_build1.py`, `test_build3.py`, `test_planner_basic.py` | устаревшие дубли/тесты |
| `tests/integration/` | сломан (`CycleResult`) |
| `.claude-review-20260731/`, `.deepseek-review-20260731/`, `.publish-qwen/` | обзорные артефакты ИИ-команд |
| `AI_TEAM_HANDOFF.md`, `TEAM_COORDINATION.md`, `TASKS_FOR_MODELS.md`, `IDEA.md`, `MODEL_CARD`, `ALIASES` | коорд-мусор (перенести в `docs/` при желании) |

### 2.2 Оставить (рабочее ядро — переезжает в `uni/` как есть)
- `uni/agent.py`, `event_loop.py`, `browser_session.py`, `config.py`, `contracts.py`, `state.py`, `working_memory.py`, `session_log.py`, `roles/loader.py`, `roles/assistant.md`, `tools/`, `capabilities/*`, `skills/`.
- `uni/config.yaml` (рабочий конфиг).
- `tests/fasttrack/` — рабочие unit-тесты (перенести в `uni/tests/` или оставить `tests/`).
- `ru_RU-irina-medium.onnx` + `.json` — голос (положить в `uni/` или `uni/assets/`).
- `docs/` — все отчёты/дизайны.
- `pyproject.toml`/`requirements.txt` (рабочие, из `uni/`) — поднять наверх как единый манифест.
- `AGENTS.md`, `ARCHITECTURE.md`, `BUILD_STATUS.md`, `README.md`, `ROADMAP.md` — доки (обновить пути).

### 2.3 Результат структуры
```
C:\LLM\UNI\
├── uni/                 # ЕДИНСТВЕННЫЙ рабочий пакет (git-репо)
│   ├── agent.py, event_loop.py, browser_session.py, config.py, contracts.py,
│   │   state.py, working_memory.py, session_log.py
│   ├── capabilities/    # base, browser, camera, computer, memory, speech, vision, xtoys, registry
│   ├── tools/           # definitions, executors, registry, __init__
│   ├── roles/           # loader.py, assistant.md (+ новые роли)
│   ├── skills/
│   ├── assets/          # ru_RU-irina-medium.onnx, .json
│   ├── tests/fasttrack/ # рабочие unit-тесты
│   ├── config.yaml
│   └── pyproject.toml / requirements.txt
├── docs/                # отчёты + дизайны
├── AGENTS.md, ARCHITECTURE.md, BUILD_STATUS.md, README.md, ROADMAP.md
```
**Никаких `uni/uni/`, никаких `Uni-*`, `Claude/`, `backup/`.**

> Примечание: `uni/` уже отдельный git-репо. Консолидация = очистка внутри `uni/` + удаление соседей наверху. `git` не используется для удаления (нет коммитов по истории) — чистим файловой системой, но **сначала** делаем `git -C uni status` и при желании `git -C uni add -A && git -C uni commit -m "pre-refactor snapshot"` как страховку (по желанию пользователя).

---

## 3. Feature A — Запуск приложений с откатом на «мышь + зрение»

### 3.1 Идея
`xtoys.open` и `computer.launch_app` могут упасть (как в логе: `Target page... closed` из-за headless без дисплея). Нужен **fallback**: если команда не открыла приложение — UNI ищет его окно/иконку через `vision.find_desktop_element` (компьютерное зрение), кликает мышью (`computer.click`), ждёт появления окна (`computer.focus_app`/`focus_window`), и только потом считает успехом.

### 3.2 Точки интеграции (какие файлы трогаем)
- `uni/capabilities/xtoys.py` — `open()`: обернуть вызов `search_or_open` в `try`; при `success=False` → вызвать новый `AppLauncher.launch_with_vision_fallback(session, title="XToys")`.
- `uni/capabilities/computer.py` — `launch_app()` уже умеет `Popen`. Добавить: если `Popen` вернул окно, но оно не поднялось за N сек → тоже fallback.
- **Новый модуль** `uni/capabilities/app_launcher.py` (или методы в `VisualUIOperator`):
  ```python
  class AppLauncher:
      def __init__(self, tool_executor, vision, computer, timeout=15): ...
      async def launch(self, *, app_name, window_title, exe_path=None, desktop_shortcut_text=None):
          # 1. Попытка командой (Popen / xtoys.open)
          # 2. Если не поднялось: vision.find_desktop_element(window_title or desktop_shortcut_text)
          # 3. computer.click(x,y) по центру найденного элемента
          # 4. Ждать computer.focus_app(window_title) с poll каждые 1с до timeout
          # 5. Вернуть ToolResult(success=bool)
  ```
- `uni/visual_ui_operator.py` — расширить `VisualUIOperator` методом `launch_app_with_fallback(...)` (уже есть `focus_app`, `click_visible`, `open_url_in_app` — переиспользуем).
- `uni/event_loop.py` — в `_free_form`/direct-команды добавить распознавание «запусти <app>» → маршрут на `AppLauncher`.

### 3.3 Безопасность
- Fallback **не трогает** XToys-устройство (интенсивность/toggle) — только открывает окно/вкладку.
- Клики только по найденным VLM-координатам с проверкой `width/height` (уже есть `parse_spatial_location` с лимитами).
- Таймауты на всё (`asyncio.wait_for`).

### 3.4 Псевдокод `launch`
```
async def launch(app_name, window_title):
    direct = await try_direct(app_name)          # Popen / xtoys.open
    if direct.success and await wait_window(window_title, 3s):
        return direct
    located = await vision.find_desktop_element(window_title)
    if not located.success:
        located = await vision.find_desktop_element(f"{app_name} shortcut on desktop")
    if not located.success:
        return ToolResult(False, "Не нашла икону/окно приложения на экране")
    x,y = center(located.data)
    await computer.click(x, y)
    ok = await wait_window(window_title, timeout=15s)
    return ToolResult(ok, "Запущено через клик мышью" if ok else "Не появилось окно")
```

---

## 4. Feature B — Фоновый цикл скриншотов (UNI «видит» экран постоянно)

### 4.1 Идея
Пока UNI слушает/ждёт команду, в фоне каждые 15–20с: `screenshot` рабочего стола → `vision.analyze_desktop` (VLM) → краткое описание в `WorkingMemory` (ключ `screen_state`). При новой команде системный промпт/контекст берёт `screen_state` → UNI отвечает с учётом того, что реально на экране (решает проблему из лога: «это вообще не то что камера показывает» — теперь есть актуальный снимок).

### 4.2 Точки интеграции
- **Новый модуль** `uni/screen_watcher.py`:
  ```python
  class ScreenWatcher:
      def __init__(self, tool_executor, memory, interval=18.0, enabled=True): ...
      async def _tick(self):
          shot = await tool_executor.execute("vision.observe_desktop", {})  # или analyze_desktop
          if shot.success:
              desc = await tool_executor.execute("vision.analyze_desktop", {"prompt": SHORT_PROMPT})
              memory.set("screen_state", desc.data["analysis"])
      async def run(self):                       # фоновая задача
          while self.enabled:
              await self._tick()
              await asyncio.sleep(self.interval)
  ```
- `uni/agent.py` — в `initialize()` запустить `self.screen_watcher = ScreenWatcher(...); self._watcher_task = asyncio.create_task(self.screen_watcher.run())`; в `shutdown()` — `self._watcher_task.cancel()`.
- `uni/event_loop.py` — в `_free_form`/промпт добавить: «Текущее состояние экрана (обновляется автоматически): {memory.get('screen_state')}».
- `config.py` — добавить `config.screen_watcher = {enabled, interval_seconds}`.

### 4.3 Важные решения
- **Не писать каждый кадр в память целиком** — только краткое VLM-описание (экономия токенов/диска).
- **Пауза watcher во время активного действия** (чтобы не дёргать VLM параллельно с командой) — через флаг `self._busy`.
- **Нагрузка**: VLM раз в 18с — легко для локальной модели; если VLM недоступен (LLM down) — watcher просто пропускает тик (fail-open).
- **Приватность**: описание экрана пишется в `WorkingMemory` (локально, с redaction секретов уже внутри). Можно добавить флаг «не логировать screen_state в SessionLogger».

---

## 5. Feature C — Правка TTS-бага (эмодзи/спецсимволы)

### 5.1 Причина (из лога + кода)
В `speech.py:299` `print(f"TTS error: {exc}")` выводит `KeyError: '😈'`, `'0'`, `` '`' ``. Это значит `_synthesize_audio` (Piper) падает, когда текст содержит символы вне phonemizer-словаря (эмодзи, некоторые пунктуационные/технические символы). UNI часто генерирует эмодзи (😈 в логе) → TTS полностью ломается на всём ответе.

### 5.2 Решение (точка правки — `uni/capabilities/speech.py`)
Добавить **нормализацию текста перед синтезом** (`_clean_for_tts`):
```python
import re, unicodedata

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2700-\u27bf\U0000FE00-\U0000FE0F\U0000200D]",
    re.UNICODE,
)

def _clean_for_tts(self, text: str) -> str:
    # 1. Удаляем эмодзи и вариационные селекторы
    text = _EMOJI_RE.sub(" ", text)
    # 2. Заменяем технические символы, ломающие Piper
    text = text.replace("`", "").replace("'", "'").replace('"', '"')
    # 3. Убираем управляющие символы
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    # 4. Схлопываем пробелы
    text = re.sub(r"\s+", " ", text).strip()
    return text or " "
```
И в `speak()`/`_synthesize_audio` вызывать `text = self._clean_for_tts(text)` **до** `PiperVoice.synthesize`.

### 5.3 Доп. улучшение
- Разбивать длинный текст на предложения и синтезировать по частям — если одна часть упадёт, остальные озвучатся (частичный успех вместо полного провала).
- Логировать ошибку в `session_logger`, а не `print`.

---

## 6. Что я НЕ буду менять без вашего «да» (по запросу)
- Код на диске **не трогаю** до вашего решения после консультации с другим ИИ.
- Удаление файлов — сделаю **только** после явного подтверждения (и сначала snapshot через `git` внутри `uni/`, раз это репо).

## 7. Оценка объёма (если решите реализовать)
| Шаг | Файлы | Сложность |
|---|---|---|
| Консолидация/чистка | удаление ~3000 файлов, перенос голоса/тестов/док | low (но требует подтверждения) |
| A. AppLauncher | `app_launcher.py` (new), `xtoys.py`, `visual_ui_operator.py`, `event_loop.py` | medium |
| B. ScreenWatcher | `screen_watcher.py` (new), `agent.py`, `event_loop.py`, `config.py` | medium |
| C. TTS-clean | `speech.py` (1 метод) | low |

---

## 8. ДОПОЛНЕНИЕ: баги, вскрытые живым прогоном (2026-07-31, 23:xx)

> Прогон `py -3.12` с LM Studio (mistralai/ministral-3-3b), голос Irina, браузер-Yandex/Chromium.
> Никакие файлы не менялись. Диагноз по точным строкам кода.

### 8.1 `xtoys.open` → `Target page, context or browser has been closed`
- **Где**: `uni/browser_session.py:50-58` (`start()` повторяет без `channel` при сбое) + `uni/capabilities/xtoys.py` (`page_for_host` → `self._context.new_page()` на закрытом контексте).
- **Суть**: Chromium иногда не поднимается (headless/дисплей), контекст мёртв, а `xtoys.open` не пересоздаёт сессию → падает. **Недетерминированно** (в том же прогоне позже `xtoys.open` сработал: `OK: Вкладка XToys.app открыта`).
- **План**: в `BrowserSession` добавить `ensure_alive()` — перед любым `new_page()`/`goto` проверять `self._context` и при `is_closed()` делать `await self.close(); await self.start()`. `xtoys.open`/browser-тулы вызывают `ensure_alive()` перед действием.

### 8.2 TTS-баг шире, чем эмодзи: `KeyError: 'x'` на URL-кусках
- **Где**: `uni/capabilities/speech.py:299` `print(f"TTS error: {exc}")` ловит `KeyError` от Piper/phonemizer на символах вне словаря.
- **Факт из лога**: `TTS error: 'x'` на фразе про `x-toys.ru` (плюс ранее `'😈'`, `'0'`, `` '`' ``). Значит ломается на **любых «грязных» символах**: URL, `-`, `` ` ``, подчёркивания, эмодзи.
- **План (расширить Feature C)**: `_clean_for_tts` удаляет/транслитерирует всё вне `[а-яёa-z0-9 .,!?-]`; URL-подобные куски (`https?://...`, `x-toys.ru`) — либо дропать, либо заменять на произносимое («икс тойз точка ру»). Плюс синтез по предложениям с частичным успехом.

### 8.3 Грязный URL от STT → `browser.navigate` не санирует
- **Где**: `parse_direct_command` (event_loop.py:218-224) + `BrowserSession.navigate` (browser_session.py:96-102, **без санизации**).
- **Факт**: команда «сделай скрин… и поищи яндекс.браузер… там будет xtoys» после искажений STT превратилась в `browser.navigate({'url': '@url:`https://x-toys.ru/`'})` → `ERR_CONNECTION_CLOSED` (Playwright получил `@url:`...``).
- **План (Feature D)**: в `navigate` очистить URL — срезать префиксы `@url:`, `` ` ``, обёртки, лишние пробелы, нормализовать scheme. Regex команды тоже чистить вход.

### 8.4 LLM-down → спам заглушкой на каждой команде
- **Где**: `_free_form` (event_loop.py:709-713) возвращает фразу при `response.error`; многие фразы («сделай скрин экрана и скажи что видишь») **не матчатся** в `parse_direct_command` → уходят в `_free_form` → спам.
- **План (Feature E)**: кэш `self._llm_available` на ~60с (не повторять заглушку подряд); при down прямые команды **всё равно** исполняются; расширить regex на составные фразы (скрин + «скажи что видишь», «поищи <X> на скрине»).

### 8.5 Интерфейс: перемешивание «Команда:» и ввода, шумное STT
- **Где**: `_schedule_input` (event_loop.py:768-776) + voice producer слушает, пока задача активна.
- **План (Feature F)**: «окно тишины» — не слушать, пока `_audio_lock`/фон-задача активны; дропать STT короче ~3 символов и с high `no_speech_prob` (логика уже есть в `speech.py`, но порог не используется для фильтрации пустого ввода в цикле).

### 8.6 Подтверждённые хорошие места (не трогать)
- `VisualUIOperator`, HITL `internal.confirm_send` (сообщения не уходят без «да отправляй»), `camera.start(notice_ack=True)` (согласие до камеры), `page_for_host` (поиск вкладки по хосту), `max_intensity` защита, redaction секретов.
- `xtoys.open` в итоге **работает** — значит браузер поднимается, проблема в гонке/повторе, не в принципе.

### 8.7 Старый баг из аудита — живой
- `event_loop.py:707`: `get_tool_schemas(set(self.capabilities.get_names()))` — сигнатура `(enabled_capabilities=None)`; аргумент игнорируется, **фильтрации нет** → LLM видит схемы `xtoys_open`/`browser_navigate`, рассинхронизированные с `ToolExecutor._ROUTING` (`xtoys.open`). Работает через `_API_ALIASES`, но источник правды двойной. **План**: генерировать схемы из самих capability (единый источник).

---
*Это проект. Никакие файлы не изменены, ничего не удалено.*
