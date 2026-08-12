# REPORT_006 — Аудит 2 падающих fasttrack-тестов (честно)

Дата: 2026-08-12 (ночь). Диспетчер: Hermes SOLO.

## Полный pytest: 251 passed, 2 failed (эти два)
1. `tests/fasttrack/test_camera.py::CameraCapabilityTests::test_camera_starts_without_notice`
   - Падает: `assertTrue(result.success)` после `CameraCapability.start(notice_ack=False)`.
   - Причина: реальная реализация `uni/capabilities/camera.py` возвращает `success=False`
     при `notice_ack=False` (требует реальной камеры/нотификации). Тест ожидает обратное.
   - Код `camera.py` я НЕ трогал в этой сессии (последние правки — xtoys/webui, не camera).
   - Pre-existing. Не чинил (вне scope директивы, риск сломать camera-логику).

2. `tests/fasttrack/test_realtime_role.py::RealtimeRoleTests::test_role_loads_independently_of_cwd`
   - Падает: `assertIn("Госпожа", role.system_prompt)` — но роль `xtoys_mistress`
     теперь содержит промпт "Dorch" (спокойный техоператор), а НЕ "Госпожа".
   - Причина: роль была переименована/переписана в прошлых коммитах (xtoys refactor,
     см. `65b0dc7 refactor(xtoys)`), а тест остался со старой строкой.
   - ТЕСТ УСТАРЕЛ, не код. Я НЕ правил role-промпты (риск сломать XToys/Intiface-логику).

## Вывод
Оба failure — pre-existing, в коде, который я не менял. Чинить их = править camera/role
вне текущей директивы. Рекомендую отдельную задачу/ADR:
- Для #1: либо поправить тест под реальное поведение camera, либо доработать camera capability.
- Для #2: обновить тест (ожидать "Dorch" или убрать проверку "Госпожа").

Не симулирую успех — тесты реально красные, но не по моей вине.
