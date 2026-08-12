# Задача: Честный аудит 2 падающих fasttrack-тестов

## СЕКЦИЯ HERMES
Полный pytest показывает 2 fails: tests/fasttrack/test_camera.py::test_camera_starts_without_notice
и tests/fasttrack/test_realtime_role.py::test_role_loads_independently_of_cwd.
Не чинить вслепую (код camera/role я не трогал в этой сессии). Напиши в
`uni-hermes/outbox/REPORT_fasttrack_audit.md`: что именно падает, какой код
затронут, нужен ли ADR/отдельная задача. Честно — не симулируй успех.
