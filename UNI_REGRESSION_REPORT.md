# UNI_REGRESSION_REPORT (B-07)

_Сгенерирован: 2026-08-11T15:30:06_

## Статус: ✅ GREEN

## 10× Smoke (импорт/инициализация ключевых модулей)
- passed: 10
- failed: 0
- exit: 0

## 3× Integration (сценарии act_on_screen)
- passed: 3
- failed: 0
- exit: 0

## Итого
- total passed: 13
- total failed: 0

## Как запустить вручную
```
cd C:\LLM\UNI
PYTHONPATH=C:\LLM\UNI UNI_NO_DISPLAY_CALIBRATION=1 C:\LLM\python312\python.exe -m pytest tests/test_regression_smoke.py tests/test_regression_integration.py -q
```
