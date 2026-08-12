# Задача 009: Обновить устаревшие fasttrack-тесты

## СЕКЦИЯ HERMES/COORDINATOR
2 теста падают (pre-existing, не по вине этой сессии):
- test_camera_starts_without_notice: CameraCapability.start(notice_ack=False) -> success=False.
  Либо поправить тест под реальное поведение, либо доработать camera capability.
- test_role_loads_independently_of_cwd: роль xtoys_mistress теперь "Dorch", не "Госпожа".
  Тест устарел — обновить ожидание.
Требует ADR/отдельной задачи (не в рамках V-багов оверлея).
