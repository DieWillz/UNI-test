# UNI — Полный аудит проекта

**Автор:** Laguna (Hermes Agent)  
**Дата:** 2026-09-11  
**Версия проекта:** UNI прототип (v1.0-dev)  
**Канонический код:** `C:\LLM\UNI\uni`

---

## 1. Глобальная картина

### 1.1. Архитектурная диссонанс

**Манифест (`UNI_CONCEPT.md`, `UNI_MANIFESTO_v2.6.md`) обещает:**
- 🤖 **AI Council** — Coordinator, Researcher, Skeptic, Planner, Executor, Vision, Auditor (эстафета задач)
- 🤖 **Shared State** — Working Memory + Shared Task Store
- 🤖 **Identity Core** — User Model, самообучение, адаптивная личность
- 🤖 **IIE (Invisible Improvement Engine)** — тихое улучшение
- 🤖 **Reflection Loop** — рефлексия после задач
- 🤖 **Федерация UNI** — обмен навыками между экземплярами
- 🤖 **Long-term Goal Manager** — долгосрочная цель пользователя

**Что реально существует в коде:**
- ✅ **Event Loop** — маршрутизация команд → инструменты
- ✅ **Capabilities**: Browser, Computer (Windows UIA), Camera, Speech (TTS+STT), Vision (VLM), XToys
- ✅ **VisualUIOperator** — fallback для некоторых действий
- ✅ **OperatorRuntime** — планирование + исполнение + верификация (частично реализован как MissionExecutor)
- ✅ **Roles** (3 роли: coordinator/hermes, uni, developer)
- ❌ **AI Council** — несуществует. Нет Researcher, Skeptic, Planner, Auditor как отдельных агентов.
- ❌ **Shared State** — нет единого хранилища задач
- ❌ **User Model** — нет модели пользователя
- ❌ **Continual Learning Engine** — нет обучения
- ❌ **Skill Evolution** — нет эволюции навыков
- ❌ **Reflection Loop** — нет рефлексии
- ❌ **IIE** — нет движка незаметного улучшения

**Вывод:** ~90% концепциональных элементов манифеста не реализованы. Это прототип с рабочей "оболочкой", но без "мозга" в понимании манифеста.

---

## 2. Структура проекта

```
C:\LLM\UNI\
├── uni/                           # Канонический код (авторитетный)
│   ├── __main__.py                # Точка входа CLI
│   ├── agent.py                   # Сборка Agent (Brain + capabilities + EventLoop)
│   ├── brain.py                   # LLM клиент
│   ├── config.py                  # Конфиг (Pydantic)
│   ├── contracts.py               # Договоры (ActionResult, TaskOutcome, etc.)
│   ├── event_loop.py              # Главный цикл
│   ├── visual_ui_operator.py      # Fallback оператор
│   ├── capabilities/              # Capabilities (напр. Browser, Computer)
│   ├── council/                   # AI Council (provider.py, round.py, participants.py)
│   ├── operator/                  # Оператор (runtime, planner, executor, perception)
│   ├── roles/                     # Роли
│   ├── webui/                     # Веб-интерфейс (server.py ~2600 строк)
│   ├── desktop/                   # Electron overlay
│   ├── autonomous.py              # Автономный режим
│   └── check_architecture.py      # Аудит архитектуры
├── tests/                         # 264 теста (все проходят)
├── config.yaml                    # Конфигурация
├── UNI PROJECT BRIEF.md           # Краткое описание
├── UNI_MANIFESTO_v2.6.md          # Манифест
├── UNI_CONCEPT.md                 # Концепция
└── COMPUTER_VISION_CONTROL.md     # Руководство управления ПК
```

---

## 3. Архитектурный аудит по слоям

### 3.1. Event Loop (`uni/event_loop.py` — 1194 строк)

**Что делает:**
- Принимает пользовательский ввод (текст/голос)
- Роутит на `DirectCommand` (xtoys, camera, speech) или свободный ответ
- Свободный ответ → `brain.chat()` с `get_tool_schemas()`
- Tool вызовы → `tool_executor.execute()`
- Наблюдения → `brain.chat()` с tool results

**Проблемы:**
- 🔴 **Роутинг основан на regex-маркерах** — список `_ACTION_MARKERS` и `_LAUNCH_MARKERS` в `routing.py`. Это просто список слов, который легко "сломать" перефразированием.
- 🟡 **Нет единого поручения управления компьютером** — `event_loop.py` сама маршрутизирует на `tool_executor.execute("computer.launch", ...)`, а `OperatorRuntime` — это отдельный путь. Возникает дублирование.
- 🟡 **Нет структурированной классификации** — нет отделения "разговор" / "поручение" / "продолжение задачи" / "отмена".
- 🟡 **Автономный режим** (`autonomous.py`, 639 строк) — работает как отдельный цикл, не интегрирован с основным Event Loop.

**Файлы для внимания:** `event_loop.py`, `operator/routing.py`, `operator/runtime.py`

---

### 3.2. Маршрутизация задач (`uni/operator/routing.py` — 46 строк)

**Что делает:**
- `looks_like_operator_task(text)` — определяет, поручение управлять компьютером или нет
- Использует маркеры: `_ACTION_MARKERS`, `_LAUNCH_MARKERS`, `_COMPUTER_CONTEXT_MARKERS`

**Проблемы:**
- 🔴 **Только keywords, нет семантики** — как описано в директиве пункт 5
- 🔴 **Легко обойти** — "отвори Пект" вместо "открой Paint" не сработает
- 🟡 **Нет fallback к классификации модели** — нет структурированного подхода

**Файл для внимания:** `operator/routing.py`

---

### 3.3. Оператор (Operator Runtime — `uni/operator/runtime.py` — 88 строк)

**Что делает:**
- `OperatorRuntime` — обёртка над `MissionExecutor`, который:
  - Планирует (`MissionPlanner`)
  - Исполняет (`MissionExecutor`)
  - Верифицирует (`PostconditionVerifier`)

**Проблемы:**
- 🟡 **Нет визуализации в WebUI** — состояние задачи не подаётся в админку
- 🟡 **Нет связи с Event Loop** — `event_loop.py` не вызывает `operator.run()` для поручений
- 🟢 **Хорошая верификация** — `PostconditionVerifier` требует независимого наблюдения

**Файлы для внимания:** `operator/runtime.py`, `operator/executor.py`, `operator/planner.py`

---

### 3.4. Планировщик (`uni/operator/planner.py` — 265 строк)

**Что делает:**
- `MissionPlanner.plan(goal, scene)` — запрашивает план у LLM
- Валидирует JSON через pydantic (`MissionPlan`)
- Один attempt на исправление формата

**Проблемы:**
- 🔴 **LLM выбирает действия** — это нарушает принцип "LLM не выбирает метод выполнения" (директива пункт 5)
- 🟡 **Есть попытка строгой валидации** — `Postcondition` обязательна, `target` должен быть объектом
- 🟢 **Хорошая система постусловий** — есть `parse_plan_text()` с нормализацией

**Файл для внимания:** `operator/planner.py`

---

### 3.5. Исполнитель (`uni/operator/executor.py` — 419 строк)

**Что делает:**
- `MissionExecutor.run(goal)` — основной цикл:
  - Наблюдение → план → выполнение шага → новое наблюдение → проверка постусловия
- `InputBroker` — сериализация физического ввода
- `RecoveryEngine` — bounded recovery

**Хорошие моменты:**
- ✅ **Цикл наблюдение → действие → новое наблюдение** — реализован согласно директиве пункт 7
- ✅ **InputBroker** — сериялизация мыши/клавиатуры
- ✅ **RecoveryEngine** — bounded recovery, не бесконечный цикл
- ✅ **PostconditionVerifier** — верификация после каждого действия

**Проблемы:**
- 🟡 **Нет связи с админкой** — состояние задачи не подаётся в WebUI
- 🟡 **Нет STOP-состояния в WebUI**

**Файл для внимания:** `operator/executor.py`, `operator/input_broker.py`

---

### 3.6. Перцепция (`uni/operator/perception.py` — 80 строк)

**Что делает:**
- `PerceptionBroker.observe()` — объединяет Browser + UIA + OCR + Vision
- `resolve_desktop(target)` — резолвит target через UIA → OCR → Vision

**Проблемы:**
- 🔴 **Один retry чтения UIA** — как описано в симптомах пункта 6
- 🔴 **OCR confidence threshold = 0.8** — блокирует валидные результаты (0.7)
- 🟡 **Нет fallback от CDP к Windows** — при недоступном CDP не пробует Windows-путь

**Файл для внимания:** `operator/perception.py`, `tools/local_vision_fallback.py`

---

### 3.7. Windows Provider (`uni/operator/windows_provider.py` — 166 строк)

**Что делает:**
- `WindowsProvider.inspect()` — UIA snapshot активного окна
- `WindowsProvider.act()` — выполнение desktop-действий через UIA/мышь

**Хорошие моменты:**
- ✅ **UIA с fallback на мышь** — если UIA не видит элемент, fallback на координаты
- ✅ **Серийный ввод** — через InputBroker
- ✅ **Один retry чтения UIA**

**Проблемы:**
- 🔴 **Нет обнаружения видимых окон** — использует `computer.list_visible_windows()`
- 🔴 **Нет восстановления свёрнутого окна** — только `focus_app`
- 🟡 **Нет сопоставления имени программы, exe и заголовка** — только по `app` имени

**Файл для внимания:** `operator/windows_provider.py`, `capabilities/computer.py`

---

### 3.8. Веб-UI и админка (`uni/webui/server.py` — ~2600 строк)

**Что делает:**
- HTTP сервер на порту 8787
- API endpoints для всех capabilities
- Веб-интерфейс с вкладками

**Проблемы:**
- 🔴 **Нет связи с OperatorRuntime** — админка не показывает состояние задачи
- 🔴 **`ConnectionAbortedError`** — не обрабатывается корректно
- 🟡 **Нет кнопки STOP для задачи**
- 🟡 **Нет отображения текущего шага**

**Файлы для внимания:** `webui/server.py`, `webui/index.html`

---

### 3.9. Capabilities

#### Browser (`uni/capabilities/browser.py` — 7527 строк)
- ✅ Browser Automation через CDP/Playwright
- ✅ DOM-инспекция, клики, заполнение
- 🔴 **Нет выбора существующего окна браузера** — пытается запустить новый

#### Computer (`uni/capabilities/computer.py` — 1613 строк)
- ✅ UIA, мышь, клавиатура
- ✅ Человеко-подобные движения мыши
- ✅ Blacklist опасных команд
- ✅ Action badge (визуальный индикатор)
- 🟡 **Нет OCR** — используется как fallback через `local_vision_fallback.py`

#### Speech (`uni/capabilities/speech.py` — 644 строк)
- ✅ TTS (Piper/Silero)
- ✅ STT (faster-whisper)
- 🟡 **Ошибка TTS** — "TTS не вернул аудио" в консоли

#### Vision (`uni/capabilities/vision.py` — 1040 строк)
- ✅ VLM через LM Studio
- ✅ Анализ экрана/файлов
- 🟡 **Зависит от наличия VLM** — без неё не работает

#### Camera (`uni/capabilities/camera.py` — 382 строк)
- ✅ Управление камерой

#### XToys (`uni/capabilities/xtoys.py` — 27572 строк)
- ✅ Управление устройством
- ✅ Safety gates (max_intensity, notice_ack, ESC-stop)

---

## 4. Маршрутизация и классификация

### Текущее состояние (`event_loop.py` + `operator/routing.py`):

1. **Пользовательский ввод** → `EventLoop._process_input()`
2. **Парсинг direct commands** — regex на ключевые слова (xtoys, camera, intensity)
3. **Если не direct** → `looks_like_operator_task(text)` из `routing.py`
4. **Если looks_like_operator_task → True** → `operator.run(goal, permissions)`
5. **Иначе** → свободный чат с `brain.chat()`

### Проблемы:

- 🔴 **Маршрутизация на keywords** — не учитывает семантику
- 🔴 **Разные формулировки попадают в разные пути** (симптом 2)
- 🔴 **Нет единого состояния задачи** — нет понятия "продолжить задачу"

---

## 5. Анализ проблем из директивы

### Симптом 1: `cdp_attach_failed_no_browser_launched`
- **Причина:** `browser.navigate` пытается подключиться к CDP, а не использовать существующее окно
- **Файл:** `browser_session.py`, `operator/browser_provider.py`
- **Решение:** Добавить fallback на Windows-управление окнами браузера

### Симптом 2: «используй мышку» vs «используя мышку»
- **Причина:** разные формулировки попадают в разные маршруты
- **Файл:** `operator/routing.py`
- **Решение:** Унифицировать классификацию

### Симптом 3: модель заявляла, что нет Windows
- **Причина:** роль `uni` не знает о существующем `OperatorRuntime`
- **Файл:** `uni/roles/uni.md`
- **Решение:** обновить роль для знания о возможностях

### Симптом 4: невалидные планы
- **Причина:** LLM выдаёт невалидный JSON
- **Файл:** `operator/planner.py`
- **Решение:** лучше валидация, строгие схемы

### Симптом 5: `element_value_mismatch`
- **Причина:** клик в адресную строку вместо ввода текста
- **Файл:** `operator/executor.py`, `operator/verifier.py`
- **Решение:** использовать `operator.desktop.fill` вместо `click` + `press`

### Симптом 6: `active_window: {}`, `element_count: 0`
- **Причина:** UIA не доступен
- **Файл:** `operator/windows_provider.py`, `capabilities/computer.py`
- **Решение:** fallback на OCR/vision

### Симптом 7: выбор окна по `chrome.exe`
- **Причина:** распознаёт `chrome`, но не `chrome.exe`
- **Файл:** `operator/planner.py` (строка 102-112)
- **Решение:** добавить алиасы для exe-имен

### Симптом 8: «Анализ рабочего стола завершен»
- **Причина:** модель возвращает текст вместо выполнения
- **Файл:** `event_loop.py`, `operator/planner.py`
- **Решение:** запретить планировать без наблюдения

### Симптом 9: фоновые запросы к LM Studio
- **Причина:** `autonomous.enabled` и `auto_start_session` включены
- **Файл:** `config.yaml`, `autonomous.py`
- **Решение:** `auto_start_session: false` (уже исправлено)

### Симптом 10: TTS ошибки
- **Причина:** провайдер/голос не соответствуют конфигурации
- **Файл:** `capabilities/speech.py`
- **Решение:** логировать причину, не молча заменять

### Симптом 11: `ConnectionAbortedError: WinError 10053`
- **Причина:** клиент разорвал соединение
- **Файл:** `webui/server.py`
- **Решение:** обрабатывать корректно, не засорять консоль

---

## 6. Список работ (To-Do)

### Этап 1: Маршрутизация и классификация (приоритет: 🔴)
- [ ] Объединить `event_loop.py` и `OperatorRuntime` в один путь
- [ ] Добавить структурированную классификацию (не только keywords)
- [ ] Обновить роль `uni` для знания о возможностях
- [ ] Нормализовать разные формулировки ("открой" / "отвори")

### Этап 2: Окна и физический ввод (приоритет: 🔴)
- [ ] Интегрировать `windows_provider.py` с `computer.py`
- [ ] Добавить восстановление свёрнутого окна
- [ ] Сопоставление имени программы, exe и заголовка
- [ ] Подтверждение активного окна перед вводом

### Этап 3: Валидация планов (приоритет: 🟠)
- [ ] Strict JSON schema для планов
- [ ] База знаний для программных планов
- [ ] Запрет на планирование без наблюдения

### Этап 4: Оценка возможностей (приоритет: 🟠)
- [ ] Статус компонентов в runtime
- [ ] Различие: реализовано / доступно / разрешено / выполнено / подтверждено
- [ ] Честные ответы при блокерах

### Этап 5: Админка (приоритет: 🟡)
- [ ] Коннект к реальному жизненному циклу задачи
- [ ] STOP/пауза кнопки
- [ ] Отображение текущего шага и сцены
- [ ] Обработка ConnectionAbortedError

---

## 7. Заключение

Проект UNI — это мощный прототип с хорошей архитектурной идеей (разделение Intelligence/Agency/Identity, цикл Observe→Think→Act→Verify), но **в коде реализовано менее 10% от заявленного в манифесте**.

Ключевые сильные стороны:
1. ✅ Чёткий цикл верификации (Auditor)
2. ✅ Сериализация физического ввода (InputBroker)
3. ✅ Safe shutdown (STOP)
4. ✅ Архитектурные тесты (264 теста, все проходят)

Ключевые слабости:
1. ❌ Маршрутизация на keywords вместо семантики
2. ❌ AI Council не реализован
3. ❌ Нет связи между админкой и OperatorRuntime
4. ❌ OCR confidence threshold = 0.8 блокирует валидные результаты
5. ❌ Нет fallback CDP → Windows для браузера

**Рекомендация:** Сосредоточиться на этапах 1-3 (маршрутизация, окна, валидация), а не на создании новых модулей. Весь необходимый код уже существует — нужно правильно соединить существующие компоненты.

---

*Отчёт создан Laguna (Hermes Agent), 2026-09-11.*
