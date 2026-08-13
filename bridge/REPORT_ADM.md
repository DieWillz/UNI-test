# ==ОТЧЁТ== Hermes — ФАЗА 8 (Админка полного контроля, ADM-01..ADM-10)

**Директива:** Дополнение №2 (2026-08-13), ФАЗА 8 (ADM).
**Ветка:** `clean/august-2026`
**Дата:** 2026-08-13

## Что сделано

| ID | Статус | Пруф |
|----|--------|------|
| ADM-01 | DONE | `uni/webui/admin_api.py` (новый модуль); GET-маршруты в `server.py` (блок `/api/admin/*`, только 127.0.0.1) |
| ADM-02 | DONE | POST `/api/admin/actions` (whitelist + confirm для опасных) в `server.py` → `_handle_admin_action` |
| ADM-03 | DONE | `uni/webui/v3/` (index.html + admin.js + admin.css), сайдбар 6 вкладок, авто-обновление 3с, токены оверлея |
| ADM-04 | DONE | Дашборд: stack/hw/git/pytest/фаза/счётчики/аудио (INT-03) |
| ADM-05 | DONE | `runtime/admin/phases.json` (ретро-заполнен 0..8 + 9 BLOCKED) |
| ADM-06 | DONE | Логи: source/level-селекторы, авто-скролл (через `/api/uni/logs`) |
| ADM-07 | DONE | Настройки: ui_variant/role/consent/autostart/opacity → `state.json`; кнопки оверлея |
| ADM-08 | DONE | Агенты: таблица heartbeats (жив/мёртв/мин) |
| ADM-09 | DONE | Регресс: pytest 317 passed; node --check OK; пользовательский WebUI не затронут |
| ADM-10 | DONE | Этот отчёт + curl-примеры ниже |

## curl-примеры (все эндпоинты, с localhost)

```bash
# Стек (pid/порт/модель)
curl http://127.0.0.1:8787/api/admin/stack
# Железо (VRAM/RAM/CPU). Нет данных -> «—»
curl http://127.0.0.1:8787/api/admin/hw
# Git (ветка/коммит)
curl http://127.0.0.1:8787/api/admin/git
# Фазы/задачи/backlog/locks
curl http://127.0.0.1:8787/api/admin/dev
# Агенты (heartbeats)
curl http://127.0.0.1:8787/api/admin/agents
# Статистика (счётчики + pytest)
curl http://127.0.0.1:8787/api/admin/stats
# Список отчётов
curl http://127.0.0.1:8787/api/admin/reports
# Содержимое отчёта (path-traversal заблокирован)
curl "http://127.0.0.1:8787/api/admin/reports/REPORT_FINAL.md"

# Действия (whitelist). Опасные -> confirm:true
curl -X POST http://127.0.0.1:8787/api/admin/actions \
  -H 'Content-Type: application/json' \
  -d '{"action":"create_stop_txt","params":{}}'
curl -X POST http://127.0.0.1:8787/api/admin/actions \
  -H 'Content-Type: application/json' \
  -d '{"action":"set_ui_variant","params":{"v":"v3"}}'
curl -X POST http://127.0.0.1:8787/api/admin/actions \
  -H 'Content-Type: application/json' \
  -d '{"action":"run_pytest","params":{},"confirm":true}'
# Опасное без confirm -> 400:
curl -X POST http://127.0.0.1:8787/api/admin/actions \
  -H 'Content-Type: application/json' -d '{"action":"stop_stack"}'
# Неизвестное -> 400:
curl -X POST http://127.0.0.1:8787/api/admin/actions \
  -H 'Content-Type: application/json' -d '{"action":"hack"}'
```

## Живые пруфы (выполнено на целевой машине, не симуляция)
- `admin_hw()` вернул реальный GPU: VRAM free 421 MiB / used 11693 MiB / util 30% (nvidia-smi доступен).
- `admin_stack()` обнаружил llama pid + модель `downloads/Qwen3-8B-Q4_K_M.gguf`, webui/electron не запущены (честно).
- `admin_git()` → ветка `clean/august-2026`.
- `admin_agents()` → 1 агент (hermes heartbeat), статус по последнему биению.
- `admin_report_content("config.yaml")` → `{"error":"not found"}` (запрет на секреты/выход за папки).
- `_handle_admin_action("set_ui_variant", {"v":"v3"})` реально записал `interface` в `uni/desktop/state.json` (затем возвращено в v4).

## Безопасность
- `/api/admin/*` отдаётся ТОЛЬКО для `127.0.0.1`/`::1` (пруф: внешний IP → 403).
- ЗАПРЕТ: ни один эндпоинт не возвращает `config.yaml`, ключи, токены (проверено: reports не выдаёт config.yaml, path-traversal отсекается `os.path.basename` + `is_relative_to`).
- Опасные действия (stop_stack/run_packaging/restart_webui) требуют `confirm:true`.

## Регресс (ADM-09)
- `pytest` (C:/LLM/python312/python.exe, PYTHONPATH=/c/LLM/UNI): **317 passed, 7 subtests passed**.
- 2 fail — **hardware-gated, НЕ регресс**: `test_speech_synthesis::test_selected_voice_exports_wav` (нужен Piper/Silero + аудио-вывод) и `test_api_desktop::test_stt_responds` (нужен живой STT/микрофон, TimeoutError). Оба не задевают мои правки (нет упоминаний audio_env_detect/use_chunker/_split_for_tts). На headless-машине без аудиоустройства — ожидаемо (DECISION).
- `node --check uni/webui/v3/admin.js`, `app.js`, `launcher.js` — OK.
- Пользовательский WebUI (`/`, `/api/chat`) не затронут; оверлей не трогал.

## Что видно в админке по каждой фазе (ADM-05 + ФИНАЛ)
- Фаза 0 (A-01..A-10): DONE, git fcd6bae.
- Фаза 1 (B/G): DONE, e50eeae.
- Фаза 2 (C): DONE, 30368b1.
- Фаза 3 (U): DONE, 17c11c6; U-07 DECISION.
- Фаза 4 (V): DONE, 571c723; V-06 DECISION.
- Фаза 5 (M): DONE, 091b0bb; M-05 DECISION.
- Фаза 6 (Q): DONE, b9428eb; Q-07 DECISION.
- Фаза 7 (F упаковка): DONE (артефакты), сборка DECISION.
- Фаза 7(INT): DONE, 11 passed.
- Фаза 8 (ADM): DONE, 12 passed.
- Фаза 9 (PKG): BLOCKED (нужен PyInstaller+Inno+целевая Win-машина).
