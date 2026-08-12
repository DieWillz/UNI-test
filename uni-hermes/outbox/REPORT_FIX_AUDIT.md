# REPORT_FIX_AUDIT — починка по внешнему аудиту (2026-08-12)

Режим: FIX-AUDIT. Ветка: `night/uni-mouse-vision`.
Исполнитель: Hermes (SOLO). Коммиты по одному на этап, НЕ в main.

## Принцип
Каждый пункт аудита ВЕРИФИЦИРОВАН по коду до починки. Не подтвердившиеся
пункты НЕ чинились (см. AUDIT_VERIFICATION.md). Никаких новых фич вне аудита.

## Статус пунктов P1–P5

| # | Пункт аудита | Верификация | Починен | Коммит |
|---|---|---|---|---|
| P1 | Мёртвая логика `_locate()` (возврат low_conf при первом неуверенном) | ПОДТВЕРЖДЁН (visual_action.py:227) | ДА (A-01) | 43f6431 |
| P2 | Рассинхрон порогов: vision success=False при conf<0.55, ветка clarify недостижима | ПОДТВЕРЖДЁН (vision.py:324, _locate ждёт success=True) | ДА (A-02) | 896d55f |
| P3 | Консолидация мыши не выполнена: mouse_show.py:30 комментарий врёт, driver.py дёргает pyautogui | ПОДТВЕРЖДЁН (driver.py методы pyautogui; + TypeError на label=) | ДА (A-03) | 1c03098 |
| P4 | SmoothMouseDriver.cancel() — заглушка release() на lock | ПОДТВЕРЖДЁН (driver.py:116-121) | ДА (A-04, в составе A-03) | 1c03098 |
| P5 | Нет независимого гейта: нет CI для тестов; тяжёлые импорты ломают import | ЧАСТИЧНО (CI нет — ДА; import ломается — НЕТ, import работает) | ДА (A-05) | (ниже) |

### P5 — уточнение верификации
- «Нет CI для тестов» — ПОДТВЕРЖДЕНО: `.github/workflows/` содержал только
  `summary.yml` (AI-суммаризация issues), НЕ тестовый CI. → Добавлен `tests.yml`.
- «uni/__init__.py / capabilities/__init__.py падают без sounddevice/PortAudio/
  torch/faster-whisper/piper» — НЕ ПОДТВЕРДИЛОСЬ в текущем окружении:
  `import uni` и `import uni.capabilities` работают, `SpeechCapability()`
  конструируется. Причина: whisper/piper уже были ленивыми; звук (sounddevice/
  soundfile) грузился на уровне модуля. → Сделал lazy-импорт sounddevice/
  soundfile/WhisperModel/PiperVoice (A-05), чтобы import НЕ зависел от PortAudio
  даже в чистом окружении. Это усиливает гейт, не ломая потребителей.

## Диффы по фиксам

### A-01 (P1) — visual_action.py `_locate()`
Реальный перебор `queries`: при `low_conf` пробует СЛЕДУЮЩУЮ формулировку;
возвращает `"low_conf"` только если ВСЕ формулировки дали low_conf. Добавлены
2 поведенческих теста (mock считает вызовы, low_conf на первых, success на
последней — проверяет, что дошло до последней).

### A-02 (P2) — vision.py + visual_action.py
- vision.py: порог `0.55` вынесен в `VISION_CONFIDENCE_THRESHOLD` (единый
  источник истины). При `conf < порога` `find_desktop_element` возвращает
  `success=False` НО с `data` (`confidence` + `low_confidence=True`) — НЕ решает
  за оркестратора (контракт success=False сохранён, другие потребители
  visual_ui_operator/app_launch НЕ сломаны).
- visual_action.py `_locate`: обрабатывает `success=False + data` как
  `low_conf_found` → ветка clarify ДОСТИЖИМА с реальным VisionCapability.
- 3 интеграционных теста (реальный VisionCapability + реальный visual_action,
  stub только VLM/скриншот).

### A-03 (P3) + A-04 (P4) — motion/driver.py (фасад) + human_mouse.py
- SmoothMouseDriver переписан как РЕАЛЬНЫЙ фасад над HumanMouseController:
  move_to/click/drag/cancel/screen_size делегируют в контроллер; wiggle/circle/
  wander/draw строят пути через trajectory и проигрывают через
  `human.play_points`. `label=` принимается (чинит TypeError в mouse_show.py).
  Комментарий mouse_show.py:30 теперь СООТВЕТСТВУЕТ коду.
- A-04: `cancel()` вызывает `human.cancel()` (threading.Event, реальное
  прерывание `_play_sync`/`_move_sync`), а НЕ `release()` на asyncio.Lock.
- human_mouse.py: добавлен `_screen_size` (win32 GetSystemMetrics, без pyautogui).
- 6 тестов делегирования (mock win32-уровня, НЕ hasattr).

### A-05 (P5) — speech.py lazy import + CI
- speech.py: sounddevice/soundfile/WhisperModel/PiperVoice — ленивые импорты
  внутри методов (с `from __future__ import annotations` типы не вычисляются).
- .github/workflows/tests.yml: pytest + check_architecture при push/PR.

## Вывод pytest (полный, аудит-релевантный набор)
```
tests/test_visual_action_loop.py       15 passed
tests/test_human_mouse.py               (в составе) passed
tests/test_audit_a02_threshold.py        3 passed
tests/test_audit_a03_mouse_facade.py     6 passed
Итого: 34 passed, 0 failed (check_architecture 0/0)
```

## Вывод check_architecture --strict
Summary: 0 error(s), 0 warning(s)

## Изменённые файлы
- uni/tools/visual_action.py (A-01, A-02)
- uni/capabilities/vision.py (A-02)
- uni/motion/driver.py (A-03/A-04, фасад)
- uni/human_mouse.py (A-03, _screen_size)
- uni/capabilities/speech.py (A-05, lazy import)
- .github/workflows/tests.yml (A-05, CI)
- tests/test_visual_action_loop.py (A-01 тесты)
- tests/test_audit_a02_threshold.py (NEW, A-02)
- tests/test_audit_a03_mouse_facade.py (NEW, A-03/A-04)

## Честное признание pre-existing проблем (НЕ чинились, вне scope)
- tests/fasttrack/test_camera.py::test_camera_starts_without_notice —
  CameraCapability.start при notice_ack=False возвращает success=False.
  Код camera.py НЕ трогал (вне аудита).
- tests/fasttrack/test_realtime_role.py::test_role_loads_independently_of_cwd —
  xtoys_mistress содержит "Dorch", тест ожидает "Госпожа". XToys — ЗАПРЕТНАЯ
  ЗОНА по инвариантам директивы. Тест устарел после xtoys-refactor.
  Требуют отдельной задачи/ADR, не чинились в рамках FIX-AUDIT.

## Как прогнать тесты в минимальном окружении
```
set PYTHONPATH=<root>
set UNI_NO_DISPLAY_CALIBRATION=1
python -m pytest tests/test_visual_action_loop.py tests/test_human_mouse.py \
  tests/test_audit_a02_threshold.py tests/test_audit_a03_mouse_facade.py -q
python scripts/check_architecture.py --strict
```
CI (.github/workflows/tests.yml) делает то же самое на push/PR.
