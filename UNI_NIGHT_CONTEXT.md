# UNI NIGHT CONTEXT PACK (для Hermes, перед каждой задачей)

## Текущая цель
Довести физическую мышь и компьютерное зрение до рабочего замкнутого контура.

## Активная задача
ID: N-04 (подключение HumanMouseController) → N-07 (visual action loop)
Owner: Hermes

## Ограничения
- канон `uni/` правится Hermes (и зеркалируется в песочницу Юни);
- не трогать config.yaml, процессы, порты 8000/8787, XToys/Intiface;
- не удалять файлы (только deprecated-пометка);
- capability НЕ импортирует capability → оркестрация в `uni/tools/visual_action.py`;
- proof of work обязателен (вывод теста/архитектуры/лог).

## Файлы задачи
- uni/capabilities/computer.py
- uni/human_mouse.py
- uni/human_motion.py
- uni/motion/driver.py (пометить deprecated)
- tests/test_human_mouse.py
- uni/tools/visual_action.py (создать)
- tests/test_visual_action_loop.py (создать)

## Файлы НЕ трогать
- config.yaml
- memory/ logs/ (кроме ночных логов)
- uni/intiface_bridge.py, xtoys_control_coordinator.py, autonomous_session.py (без отдельной задачи)

## Команды проверки
- pytest tests/test_human_mouse.py -q
- pytest tests/test_visual_action_loop.py -q
- pytest -q
- py -3.12 -m uni.check_architecture --strict  (или фактическая команда проекта)

## Последние изменения
- human_mouse.py импортируется OK (HumanMouseController есть).
- computer.py: click() на pyautogui:178.
- vision.py: analyze_screen/desktop/file работают.
---
*Hermes = context pack от 2026-08-10.*
