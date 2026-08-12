# UNI_DO_NOT_TOUCH

Без явной задачи координатора не изменять:

- `.git/`
- `config.yaml` (секреты)
- `memory/`, `logs/` (кроме ночных логов)
- `__pycache__/`, `venv/`, `node_modules/`
- `*.secret`, `*.env`
- `uni/webui/bin/`
- `UNI_LOCKS.json` — только свои блокировки
- `UNI_BOARD.md` / `UNI_TASKS_LIGHT.md` — только через координатора / Hermes
- `uni/security/`
- `uni/intiface_bridge.py`, `uni/xtoys_control_coordinator.py`, `uni/autonomous_session.py`
- `tests/` — только если задача явно требует тестов
- `uni_tandem_watchdog.ahk`, `hermes_auto.ahk` — автоматика Юни, не трогать
