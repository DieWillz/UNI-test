# AUDIT_VERIFICATION — верификация внешнего аудита (2026-08-12)

Режим: FIX-AUDIT. Ветка: `night/uni-mouse-vision`. Принцип: каждый пункт
верифицирован по фактическому коду (grep/номер строки/pytest), аудитору слепо
не верю.

## P1. Мёртвая логика в visual_action._locate()
**СТАТУС: ПОДТВЕРЖДАЕТСЯ**

Доказательство — `uni/tools/visual_action.py:211-228`:
```python
219  for q in queries:
220      res = await self._vision.find_desktop_element(q)
221      if res.success and res.data:
222          data = dict(res.data)
223          conf = data.get("confidence", 0.0)
224          if conf >= self.confidence_threshold:
225              return data
226          # найдено, но уверенность низкая — возвращаем маркер
227          return "low_conf"   # <-- ВОЗВРАТ ПРИ ПЕРВОМ ЖЕ неуверенном
228  return None
```
Цикл возвращает `"low_conf"` при первом `conf < threshold`, не пробуя
`queries[1]` и `queries[2]`. Мёртвая логика подтверждена.

## P2. Рассинхрон порогов уверенности
**СТАТУС: ПОДТВЕРЖДАЕТСЯ**

Доказательство — `uni/capabilities/vision.py:324-325`:
```python
324  if location.confidence < 0.55:
325      return ToolResult(success=False, message=f"Низкая уверенность Vision: ...")
```
`find_desktop_element` возвращает `success=False` при `conf < 0.55`.

А `_locate()` (P1, строки 221-227) для ветки `low_conf` требует
`res.success and res.data` И `conf < threshold`. Но vision.py никогда не
вернёт `success=True` с низким confidence (всегда `False`). → Ветка
`low_conf` в `_locate` **недостижима** с реальным `VisionCapability`.
Рассинхрон порогов подтверждён.

## P3. Консолидация мыши (пункт 1.2) не выполнена корректно
**СТАТУС: ПОДТВЕРЖДАЕТСЯ**

1. `uni/scenarios/mouse_show.py:30`:
```python
30  # SmoothMouseDriver теперь фасад над HumanMouseController; фасад для ...
31  self.mouse = SmoothMouseDriver(label=self.overlay)
```
Комментарий утверждает, что `SmoothMouseDriver` — фасад над
`HumanMouseController`.

2. `uni/motion/driver.py:39` класс `SmoothMouseDriver`, методы дёргают
`pyautogui` напрямую (НЕ `HumanMouseController`):
```python
24  import pyautogui
56  x, y = pyautogui.position()
61  w, h = pyautogui.size()
65  async def move_to(self, ...): ... pyautogui.moveTo(...)
```
`grep -c "HumanMouseController" uni/motion/driver.py` → 2 (только в
DEPRECATED-комментарии, который добавил Hermes 2026-08-12; в коде методов
`HumanMouseController` НЕ используется).

3. `uni/human_mouse.py:70` — `class HumanMouseController` существует, но
`SmoothMouseDriver` его НЕ вызывает.

Вывод: комментарий в `mouse_show.py:30` **не соответствует коду**.
Консолидация 1.2 выполнена некорректно (фасада нет). Подтверждается.

## P4. SmoothMouseDriver.cancel() — заглушка
**СТАТУС: ПОДТВЕРЖДАЕТСЯ**

`uni/motion/driver.py:116-121`:
```python
116  def cancel(self) -> None:
117      """Прервать текущее движение — снимает busy-лок, если занят."""
118      try:
119          self._busy.release()
120      except RuntimeError:
121          pass
```
`cancel()` только делает `self._busy.release()` (освобождает asyncio.Lock).
Цикл `_play_points` (который реально двигает мышь) НЕ проверяет флаг
отмены → `cancel()` не прерывает движение. Заглушка подтверждена.
(P4 актуален, т.к. P3 подтвердился — driver.py активен, а не deprecated-фасад.)

## P5. Нет независимого гейта (CI + тяжёлые импорты)
**СТАТУС: ЧАСТИЧНО ПОДТВЕРЖДАЕТСЯ**

### 5.1 CI для тестов — ОТСУТСТВУЕТ (подтверждается)
`.github/workflows/` содержит только `summary.yml` — это автосуммаризация
issues через AI, НЕ тестовый CI:
```yaml
name: Summarize new issues
on:
  issues:
    types: [opened]
```
Реального `.github/workflows/tests.yml` с `pytest` НЕТ. → Подтверждается.

### 5.2 Тяжёлые импорты (частично, аудитор ошибся)
Аудитор: «uni/__init__.py жёстко импортирует Agent→Brain→openai;
capabilities/__init__.py тянет speech.py→sounddevice→PortAudio; нельзя
прогнать один модуль без всего стека».

Фактическая проверка (2026-08-12, python312):
- `import uni` → **OK** (не падает).
- `import uni.capabilities` → **OK** (Capability-классы доступны).
- `tests/test_visual_action_loop.py + tests/test_human_mouse.py` →
  **23 passed** (запускаются в текущем окружении без аудио-железа).
- `uni/capabilities/speech.py:16` → `import sounddevice as sd` (жёсткий
  импорт в модуле).

Вывод: в ТЕКУЩЕМ окружении тяжёлые зависимости доступны (PortAudio есть),
поэтому импорт не падает и тесты запускаются. Но `sounddevice` импортируется
жёстко (не лениво), и в ДЕЙСТВИТЕЛЬНО ЧИСТОМ окружении (без PortAudio)
`import uni.capabilities` УПАДЁТ. Риск реален, но аудитор преувеличил
«нельзя прогнать вообще» — прогнать МОЖНО (23 passed).

**Итог P5:** отсутствие тестового CI — подтверждается (нужен fixes A-05);
жёсткие импорты — частично (риск есть, но в текущем окружении не блокирует).

## Решение по этапам
- A-01 (P1): ЧИНИТЬ (подтверждён).
- A-02 (P2): ЧИНИТЬ (подтверждён) — Вариант А (vision возвращает low_confidence=True).
- A-03 (P3): ЧИНИТЬ (подтверждён) — привести mouse_show.py комментарий в соответствие;
  driver.py уже DEPRECATED-помечен, но НЕ фасад → либо сделать фасадом, либо
  честно пометить и перенести логику. Выберу: сделать SmoothMouseDriver фасадом
  над HumanMouseController (делегирование методов).
- A-04 (P4): ЧИНИТЬ (подтверждён) — реальное прерывание через asyncio.Event.
- A-05 (P5): ЧИНИТЬ частично — добавить tests.yml CI; сделать sounddevice ленивым
  (try/except ImportError) в speech.py; не ломать существующие импорты.
