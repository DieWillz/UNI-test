# UNI — Визуальная проверка функций

**Дата:** 2026-09-11  
**Автор:** Longcat (Hermes Agent)  
**Цель:** Проверить глазами, что Юни реально работает

---

## Инструкция по проверке

Для каждой функции:
1. Запустите команду в терминале
2. **Смотрите на экран** — вы должны увидеть результат
3. Отметьте ✅ если видите ожидаемый результат, ❌ если нет

---

## 1. Управление окнами

### 1.1. Список видимых окон

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
r = asyncio.run(c.execute('list_visible_windows'))
import json
print(json.dumps(r.data, indent=2, ensure_ascii=False))
"
```

**Что увидеть:** JSON-список окон с заголовками. Должны быть окна, которые сейчас открыты на экране.

**Критерий:** ✅ Если в списке есть хотя бы 2-3 окна с правильными заголовками

---

### 1.2. Запуск Блокнота

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
r = asyncio.run(c.execute('launch', app='notepad'))
print(r.success, r.message)
"
```

**Что увидеть:** Открылось новое окно "Блокнот" на экране.

**Критерий:** ✅ Если окно Блокнота появилось

---

### 1.3. Фокус на окне

**Шаг 1:** Откройте Блокнот  
**Шаг 2:** Откройте Проводник поверх Блокнота (кликните на него)  
**Шаг 3:** Запустите:

```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
r = asyncio.run(c.execute('focus_window', title='Блокнот'))
print(r.success, r.message)
"
```

**Что увидеть:** Окно Блокнота переходит на передний план, становится активным.

**Критерий:** ✅ Если Блокнот оказался поверх Проводника

---

## 2. Управление мышью

### 2.1. Движение курсора

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
# Курсор в центр экрана
r = asyncio.run(c.execute('move', x=960, y=540))
print(r.success, r.message)
"
```

**Что увидеть:** Курсор мыши плавно движется к центру экрана.

**Критерий:** ✅ Если курсор реально двигается

---

### 2.2. Клик мышью

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
# Клик в координаты (500, 500)
r = asyncio.run(c.execute('click_human', x=500, y=500))
print(r.success, r.message)
"
```

**Что увидеть:** Курсор движется к точке (500, 500) и кликает.

**Критерий:** ✅ Если клик произошёл в указанной точке

---

## 3. Управление клавиатурой

### 3.1. Ввод текста

**Шаг 1:** Откройте Блокнот  
**Шаг 2:** Кликните в область текста  
**Шаг 3:** Запустите:

```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
r = asyncio.run(c.execute('type_unicode', text='UNI проверка работы!'))
print(r.success, r.message)
"
```

**Что увидеть:** В Блокноте появляется текст "UNI проверка работы!".

**Критерий:** ✅ Если текст ввёлся корректно

---

### 3.2. Нажатие Enter

**Продолжая в Блокноте, запустите:**

```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
c = ComputerCapability()
r = asyncio.run(c.execute('press', key='enter'))
print(r.success, r.message)
"
```

**Что увидеть:** Курсор переходит на новую строку.

**Критерий:** ✅ Если произошёл переход на новую строку

---

## 4. Управление браузером

### 4.1. Открыть сайт

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
c = BrowserCapability()
r = asyncio.run(c.execute('navigate', url='https://example.com'))
print(r.success, r.message)
"
```

**Что увидеть:** Открывается браузер (или новая вкладка) со страницей example.com.

**Критерий:** ✅ Если страница загрузилась

---

### 4.2. Поиск в интернете

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.browser import BrowserCapability
c = BrowserCapability()
r = asyncio.run(c.execute('search_web', query='погода москва'))
print(r.success)
if r.success:
    for item in r.data.get('results', [])[:3]:
        print(f'  - {item.get(\"title\", \"\")}')
"
```

**Что увидеть:** Открывается страница поиска с результатами.

**Критерий:** ✅ Если результаты поиска отображаются

---

## 5. Голос (TTS)

### 5.1. Произнести текст

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.speech import SpeechCapability
c = SpeechCapability()
r = asyncio.run(c.execute('speak', text='Привет мир Юни говорит'))
print(r.success, r.message)
"
```

**Что увидеть:** Динамики начинают воспроизводить голос, произносящий "Привет мир Юни говорит".

**Критерий:** ✅ Если слышен голос

---

## 6. Камера

### 6.1. Снимок с камеры

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.camera import CameraCapability
c = CameraCapability()
# Запуск камеры
asyncio.run(c.execute('start'))
# Снимок
r = asyncio.run(c.execute('snapshot', label='test'))
print(r.success)
if r.success:
    print('Фото сохранено:', r.data.get('path', ''))
# Остановка
asyncio.run(c.execute('stop'))
"
```

**Что увидеть:** Камера запускается (может загореться индикатор), затем фото сохраняется на диск.

**Критерий:** ✅ Если файл появился на диске

---

## 7. Зрение (VLM)

### 7.1. Анализ экрана

**Предусловие:** Должен быть запущен VLM (LM Studio или Gradio)

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.vision import VisionCapability
c = VisionCapability()
r = asyncio.run(c.execute('analyze_screen', prompt='Опиши что на экране'))
print(r.success)
if r.success:
    print('Анализ:', r.data.get('analysis', '')[:500])
else:
    print('Ошибка:', r.message)
"
```

**Что увидеть:** В терминале выводится текстовое описание содержимого экрана.

**Критерий:** ✅ Если описание соответствует тому, что на экране

---

## 8. Проверка через WebUI

### 8.1. Веб-панель

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -m uni.webui
```

**Что увидеть:**
- В браузере откроется панель на `http://127.0.0.1:8787`
- Вкладки: Чат, Компьютер, Видение, Админ

**Проверка вкладки "Компьютер":**
1. Откройте `http://127.0.0.1:8787` → вкладка "Компьютер"
2. Введите "открой блокнот" в поле ввода
3. Нажмите "Выполнить"

**Что увидеть:** Откроется Блокнот, в логе шагов будет видно выполнение.

**Критерий:** ✅ Если Блокнот открылся через веб-панель

---

## 9. Проверка через CLI

### 9.1. Интерактивный режим

**Запустите:**
```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -m uni
```

**Что увидеть:**
- Юни поздоровается голосом
- В терминале появится приглашение для ввода
- Можно вводить команды текстом

**Тестовые команды:**
- `открой блокнот` — откроется Блокнот
- `найди в интернете Python` — откроется поиск
- `что на вкладке` — Юни опишет текущую страницу

**Критерий:** ✅ Если команды выполняются

---

## 10. Итоговая таблица проверки

| Функция | Команда | Что увидеть | ✅/❌ |
|---------|---------|-------------|-------|
| Запуск Блокнота | `launch app=notepad` | Окно Блокнота | |
| Фокус на окне | `focus_window title=Блокнот` | Окно переходит вперёд | |
| Движение мыши | `move x=960 y=540` | Курсор движется | |
| Клик мышью | `click_human x=500 y=500` | Клик в точке | |
| Ввод текста | `type_unicode text=Привет` | Текст в Блокноте | |
| Нажатие Enter | `press key=enter` | Новая строка | |
| Открыть сайт | `browser.navigate url=...` | Страница в браузере | |
| Поиск в интернете | `browser.search_web query=...` | Результаты поиска | |
| Голос | `speak text=Привет` | Голос из динамиков | |
| Камера | `camera.snapshot` | Фото на диске | |
| Анализ экрана | `analyze_screen` | Описание экрана | |
| WebUI | `-m uni.webui` | Панель в браузере | |
| CLI | `-m uni` | Интерактивный режим | |

---

## Как запустить всё разом

```bash
cd C:\LLM\UNI
set PYTHONPATH=C:\LLM\UNI
C:\LLM\python312\python.exe -c "
import asyncio
from uni.capabilities.computer import ComputerCapability
from uni.capabilities.browser import BrowserCapability
from uni.capabilities.speech import SpeechCapability

async def visual_test():
    print('=== ВИЗУАЛЬНЫЙ ТЕСТ ===')
    
    # 1. Блокнот
    c = ComputerCapability()
    r = await c.execute('launch', app='notepad')
    print(f'[1] Блокнот: {r.success}')
    await asyncio.sleep(2)
    
    # 2. Ввод текста
    r = await c.execute('type_unicode', text='UNI visual test works!')
    print(f'[2] Ввод текста: {r.success}')
    await asyncio.sleep(1)
    
    # 3. Enter
    r = await c.execute('press', key='enter')
    print(f'[3] Enter: {r.success}')
    
    # 4. Браузер
    b = BrowserCapability()
    r = await b.execute('navigate', url='https://example.com')
    print(f'[4] Браузер: {r.success}')
    
    # 5. Голос
    s = SpeechCapability()
    r = await s.execute('speak', text='UNI visual test completed')
    print(f'[5] Голос: {r.success}')
    
    print('\n=== СМОТРИТЕ НА ЭКРАН ===')
    print('- Блокнот открыт с текстом UNI visual test works!')
    print('- Браузер открыт на example.com')
    print('- Голос произносит фразу')

asyncio.run(visual_test())
"
```

**Что увидеть:**
- Открытый Блокнот с текстом "UNI visual test works!"
- Открытый браузер на example.com
- Голос произносит "UNI visual test completed"

---

*Документ подготовлен Longcat (Hermes Agent), 2026-09-11. Распечатайте и отмечайте.*
