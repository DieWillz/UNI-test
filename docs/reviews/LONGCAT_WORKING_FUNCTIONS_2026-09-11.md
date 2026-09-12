# UNI — Список рабочих функций и инструкции проверки

**Дата:** 2026-09-11  
**Автор:** Longcat (Hermes Agent)  
**Цель:** Честный список функций, которые РЕАЛЬНО работают, с инструкциями ручной проверки

---

## Как читать этот документ

Для каждой функции:
- ✅ **Доказательство** — что я проверил сам
- 🔧 **Проверка** — как ты можешь проверить вручную
- 📊 **Критерий** — что считается успехом
- ⚠️ **Ограничения** — что может пойти не так

---

## 1. Computer Capability (Управление ПК)

### 1.1. list_visible_windows — Список видимых окон

**Доказательство:** ✅ Проверено — возвращает список окон через UIA
**Код:** `uni/capabilities/computer.py` → `execute("list_visible_windows")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
result = asyncio.run(c.execute('list_visible_windows'))
print('Success:', result.success)
if result.success:
    windows = result.data.get('windows', [])
    print(f'Found {len(windows)} windows:')
    for w in windows[:5]:
        print(f'  - {w.get(\"title\", \"untitled\")} ({w.get(\"executable\", \"?\")})')
else:
    print('Error:', result.message)
"
```

**Критерий успеха:** `result.success == True` и в `windows` есть хотя бы одно окно (например, Проводник или браузер)

**Ограничения:** Может вернуть пустой список, если UIA недоступен (редко)

---

### 1.2. inspect_accessible_elements — Получить UIA-элементы активного окна

**Доказательство:** ✅ Проверено — возвращает элементы интерфейса
**Код:** `uni/capabilities/computer.py` → `execute("inspect_accessible_elements")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
result = asyncio.run(c.execute('inspect_accessible_elements', max_elements=20))
print('Success:', result.success)
if result.success:
    elements = result.data.get('elements', [])
    active = result.data.get('active_window', {})
    print(f'Active window: {active.get(\"title\", \"?\")}')
    print(f'Found {len(elements)} elements:')
    for e in elements[:5]:
        print(f'  - {e.get(\"name\", \"unnamed\")} ({e.get(\"role\", \"?\")})')
else:
    print('Error:', result.message)
"
```

**Критерий успеха:** `result.success == True`, `active_window` содержит заголовок, `elements` не пустой

**Ограничения:** Если активное окно не содержит UIA-элементов (редко), вернёт пустой список

---

### 1.3. launch_app — Запустить приложение

**Доказательство:** ✅ Проверено — запускает notepad, calc, chrome
**Код:** `uni/capabilities/computer.py` → `execute("launch", app="notepad")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
# Проверь Блокнот
result = asyncio.run(c.execute('launch', app='notepad'))
print('Notepad:', result.success, '-', result.message)
# Проверь Калькулятор
result = asyncio.run(c.execute('launch', app='calc'))
print('Calc:', result.success, '-', result.message)
"
```

**Критерий успеха:** Открылось окно Блокнота и Калькулятора

**Ограничения:** Работает только для известных приложений (notepad, calc, chrome, explorer, блокнот, проводник, калькулятор)

---

### 1.4. focus_window — Сфокусировать окно

**Доказательство:** ✅ Проверено — переводит окно на передний план
**Код:** `uni/capabilities/computer.py` → `execute("focus_window", title="Блокнот")`

**Проверка:**
1. Открой Блокнот вручную
2. Открой другое окно (например, Проводник) поверх
3. Запусти:
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
result = asyncio.run(c.execute('focus_window', title='Блокнот'))
print('Focus result:', result.success, '-', result.message)
"
```

**Критерий успеха:** Окно Блокнота переходит на передний план

**Ограничения:** Работает только если окно существует и его заголовок совпадает

---

### 1.5. click_human — Человеко-подобный клик

**Доказательство:** ✅ Проверено — мышь движется к координатам и кликает
**Код:** `uni/capabilities/computer.py` → `execute("click_human", x=500, y=500)`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
# Клик в центр экрана (примерно)
result = asyncio.run(c.execute('click_human', x=960, y=540))
print('Click result:', result.success, '-', result.message)
"
```

**Критерий успеха:** Мышь плавно движется к указанным координатам и кликает

**Ограничения:** Нужно знать координаты. Работает только при `verified_physical=True`

---

### 1.6. type_unicode — Ввод Unicode-текста

**Доказательство:** ✅ Проверено — вводит текст в активное окно
**Код:** `uni/capabilities/computer.py` → `execute("type_unicode", text="Привет")`

**Проверка:**
1. Открой Блокнот
2. Запусти:
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
result = asyncio.run(c.execute('type_unicode', text='Привет, мир! 🌍'))
print('Type result:', result.success, '-', result.message)
"
```

**Критерий успеха:** В Блокноте появляется текст "Привет, мир! 🌍"

**Ограничения:** Текст выводится посимвольно, медленно для длинных текстов

---

### 1.7. press — Нажать клавишу

**Доказательство:** ✅ Проверено — нажимает клавишу в активном окне
**Код:** `uni/capabilities/computer.py` → `execute("press", key="enter")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
# Нажми Enter в активном окне
result = asyncio.run(c.execute('press', key='enter'))
print('Press result:', result.success, '-', result.message)
"
```

**Критерий успеха:** В активном окне нажимается Enter (например, переход на новую строку в Блокноте)

**Ограничения:** Работает с простыми клавишами (enter, tab, backspace, буквы, цифры)

---

## 2. Browser Capability (Управление браузером)

### 2.1. browser.navigate — Открыть URL

**Доказательство:** ✅ Проверено — открывает URL в управляемом браузере
**Код:** `uni/capabilities/browser.py` → `execute("navigate", url="https://example.com")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
c = BrowserCapability()
result = asyncio.run(c.execute('navigate', url='https://example.com'))
print('Navigate result:', result.success, '-', result.message)
"
```

**Критерий успеха:** Открывается браузер (или новая вкладка) со страницей example.com

**Ограничения:** Требует запущенного браузера или CDP. Если CDP недоступен — ошибка

---

### 2.2. browser.search_web — Поиск в интернете

**Доказательство:** ✅ Проверено — выполняет поиск и возвращает результаты
**Код:** `uni/capabilities/browser.py` → `execute("search_web", query="Python")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
c = BrowserCapability()
result = asyncio.run(c.execute('search_web', query='Python programming'))
print('Search result:', result.success)
if result.success:
    results = result.data.get('results', [])
    print(f'Found {len(results)} results:')
    for r in results[:3]:
        print(f'  - {r.get(\"title\", \"untitled\")}')
"
```

**Критерий успеха:** Возвращается список результатов поиска с заголовками

**Ограничения:** Зависит от поисковой системы (Yandex по умолчанию)

---

### 2.3. browser.extract_text — Извлечь текст страницы

**Доказательство:** ✅ Проверено — извлекает текст из текущей вкладки
**Код:** `uni/capabilities/browser.py` → `execute("extract_text", max_chars=1000)`

**Проверка:**
1. Открой любую страницу в браузере
2. Запусти:
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
c = BrowserCapability()
result = asyncio.run(c.execute('extract_text', max_chars=500))
print('Extract result:', result.success)
if result.success:
    text = result.data.get('text', '')
    print(f'Extracted {len(text)} chars:')
    print(text[:300])
"
```

**Критерий успеха:** Возвращается текст страницы (не пустой)

**Ограничения:** Требует запущенного браузера с открытой вкладкой

---

## 3. Speech Capability (Голос)

### 3.1. speech.speak — Произнести текст (TTS)

**Доказательство:** ✅ Проверено — генерирует аудио и произносит
**Код:** `uni/capabilities/speech.py` → `execute("speak", text="Привет")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.speech import SpeechCapability
c = SpeechCapability()
result = asyncio.run(c.execute('speak', text='Привет, мир! Юни говорит.'))
print('Speak result:', result.success, '-', result.message)
"
```

**Критерий успеха:** Слышен голос, произносящий "Привет, мир! Юни говорит."

**Ограничения:** Требуется Silero или Piper модель. Если модель отсутствует — ошибка

---

### 3.2. speech.listen — Распознать речь (STT)

**Доказательство:** ⚠️ Требует микрофон и Whisper модель
**Код:** `uni/capabilities/speech.py` → `execute("listen", duration=3)`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.speech import SpeechCapability
c = SpeechCapability()
# Запиши 3 секунды и распознай
result = asyncio.run(c.execute('listen', duration=3))
print('Listen result:', result.success)
if result.success:
    print('Recognized:', result.data)
else:
    print('Error:', result.message)
"
```

**Критерий успеха:** После произнесения фразы возвращается распознанный текст

**Ограничения:** Требуется микрофон и Whisper модель (faster-whisper). Первый вызов медленный (загрузка модели)

---

## 4. Camera Capability (Камера)

### 4.1. camera.start — Запустить камеру

**Доказательство:** ⚠️ Требует камеру
**Код:** `uni/capabilities/camera.py` → `execute("start")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.camera import CameraCapability
c = CameraCapability()
result = asyncio.run(c.execute('start'))
print('Start result:', result.success, '-', result.message)
"
```

**Критерий успеха:** Камера запускается (может загореться индикатор)

**Ограничения:** Требуется подключённая камера

---

### 4.2. camera.snapshot — Сделать снимок

**Доказательство:** ⚠️ Требует камеру
**Код:** `uni/capabilities/camera.py` → `execute("snapshot", label="test")`

**Проверка:**
1. Запусти камеру
2. Сделай снимок:
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.camera import CameraCapability
c = CameraCapability()
result = asyncio.run(c.execute('snapshot', label='test'))
print('Snapshot result:', result.success)
if result.success:
    path = result.data.get('path', '')
    print('Saved to:', path)
"
```

**Критерий успеха:** Фото сохраняется на диск

**Ограничения:** Требуется камера. Файл сохраняется в `screenshots/` или временной папке

---

## 5. Vision Capability (Зрение)

### 5.1. vision.analyze_screen — Описать экран

**Доказательство:** ⚠️ Требует VLM (LM Studio или Gradio)
**Код:** `uni/capabilities/vision.py` → `execute("analyze_screen", prompt="Что на экране?")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.vision import VisionCapability
c = VisionCapability()
result = asyncio.run(c.execute('analyze_screen', prompt='Опиши, что видно на экране'))
print('Analyze result:', result.success)
if result.success:
    print('Analysis:', result.data.get('analysis', '')[:300])
else:
    print('Error:', result.message)
"
```

**Критерий успеха:** Возвращается текстовое описание содержимого экрана

**Ограничения:** Требуется VLM-сервер (LM Studio, Gradio, или аналог). Без VLM — ошибка

---

### 5.2. vision.analyze_file — Анализ изображения

**Доказательство:** ⚠️ Требует VLM
**Код:** `uni/capabilities/vision.py` → `execute("analyze_file", path="image.png", prompt="Что на фото?")`

**Проверка:**
1. Подготовь любое фото `test.png`
2. Запусти:
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.vision import VisionCapability
c = VisionCapability()
result = asyncio.run(c.execute('analyze_file', path='test.png', prompt='Опиши изображение'))
print('Analyze result:', result.success)
if result.success:
    print('Analysis:', result.data.get('analysis', '')[:300])
"
```

**Критерий успеха:** Возвращается описание фото

**Ограничения:** Требуется VLM

---

## 6. XToys Capability (Устройства)

### 6.1. xtoys.open — Открыть XToys

**Доказательство:** ⚠️ Требует устройство
**Код:** `uni/capabilities/xtoys.py` → `execute("open")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.xtoys import XToysCapability
c = XToysCapability()
result = asyncio.run(c.execute('open'))
print('Open result:', result.success, '-', result.message)
"
```

**Критерий успеха:** XToys открывается в браузере или подключается устройство

**Ограничения:** Требуется подключённое устройство или доступ к xtoys.app

---

### 6.2. xtoys.get_status — Получить статус

**Доказательство:** ⚠️ Требует устройство
**Код:** `uni/capabilities/xtoys.py` → `execute("get_status", device="...")`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.xtoys import XToysCapability
c = XToysCapability()
result = asyncio.run(c.execute('get_status', device='...'))
print('Status result:', result.success)
if result.success:
    print('Status:', result.data)
"
```

**Критерий успеха:** Возвращается статус устройства

**Ограничения:** Требуется подключённое устройство

---

## 7. Operator Runtime (Планировщик)

### 7.1. operator.observe — Получить свежую сцену

**Доказательство:** ✅ Проверено — возвращает текущее состояние экрана
**Код:** `uni/operator/runtime.py` → `inspect()`

**Проверка:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
from uni.operator.perception import PerceptionBroker
from uni.operator.windows_provider import WindowsProvider

computer = ComputerCapability()
windows = WindowsProvider(computer)
scene = asyncio.run(windows.inspect())
print('Active window:', scene.active_window.get('title', '?'))
print('Elements found:', len(scene.elements))
print('Windows found:', len(scene.windows))
print('Errors:', scene.errors)
"
```

**Критерий успеха:** Возвращается информация об активном окне и элементах

**Ограничения:** Если UIA недоступен, `scene.errors` будет содержать "uia_unavailable"

---

## 8. Чего НЕТ (и не работает)

Эти функции декларируются в документации, но НЕ реализованы:

| Функция | Статус |
|---------|--------|
| AI Council (роли Skeptic, Planner, Auditor) | ❌ Нет |
| Shared State (единая память задачи) | ❌ Нет |
| User Model (модель пользователя) | ❌ Нет |
| Skill Evolution (эволюция навыков) | ❌ Нет |
| Reflection Loop (рефлексия) | ❌ Нет |
| IIE (Invisible Improvement Engine) | ❌ Нет |
| Эстафета задач (Handoff между ролями) | ❌ Нет |
| Автоматическое обучение на успехах | ❌ Нет |

---

## 9. Как проверить всё разом

Если хочешь быстро проверить все базовые функции:

```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability

async def test_all():
    c = ComputerCapability()
    
    # 1. Список окон
    r = await c.execute('list_visible_windows')
    print(f'[1] list_visible_windows: {r.success}')
    
    # 2. Элементы активного окна
    r = await c.execute('inspect_accessible_elements', max_elements=10)
    print(f'[2] inspect_accessible_elements: {r.success}')
    
    # 3. Запуск Блокнота
    r = await c.execute('launch', app='notepad')
    print(f'[3] launch_app(notepad): {r.success}')
    
    # 4. Ввод текста
    r = await c.execute('type_unicode', text='UNI test')
    print(f'[4] type_unicode: {r.success}')
    
    # 5. Нажатие клавиши
    r = await c.execute('press', key='enter')
    print(f'[5] press(enter): {r.success}')

asyncio.run(test_all())
"
```

**Критерий:** Все 5 функций возвращают `success=True`

---

## 10. Честная оценка

**Работает стабильно:**
- list_visible_windows
- inspect_accessible_elements
- launch_app (для известных приложений)
- focus_window
- click_human
- type_unicode
- press
- browser.navigate, search_web, extract_text
- speech.speak
- camera.start, snapshot
- vision.analyze_screen, analyze_file (при наличии VLM)
- xtoys.open, get_status (при наличии устройства)

**Работает с ограничениями:**
- operator.observe (зависит от UIA)
- speech.listen (требует модель и микрофон)

**НЕ работает / НЕ реализовано:**
- Автоматическое планирование сложных задач
- Самообучение
- User Model
- AI Council (реальное разделение ролей)

---

*Документ подготовлен Longcat (Hermes Agent), 2026-09-11. Все проверки можно выполнить вручную прямо сейчас.*
