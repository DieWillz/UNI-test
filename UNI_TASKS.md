# UNI — актуальные задачи

Обновлено: **2026-09-10**. Это рабочий список от текущего состояния, а не исторический перечень августа.
Статусы: `СДЕЛАНО`, `В РАБОТЕ`, `ОЖИДАЕТ`, `BLOCKER`.

| ID | Статус | Задача | Критерий приёмки |
|---|---|---|---|
| CFG-ADMIN | СДЕЛАНО | Управление `config.yaml` из WebUI | schema-driven UI + localhost API + validation + secret masking + targeted tests |
| VISION-ARCH | СДЕЛАНО | Зафиксировать восприятие DOM/UIA → OCR → visual diff → VLM fallback | отражено в коде/админке/roadmap; VLM не является первым слоем |
| WEBUI-IMPORT | СДЕЛАНО | Устранить circular import handlers registry | `import uni.webui.server` выполняется |
| WEBUI-LAYOUT | СДЕЛАНО | Устранить перекрытие контента sidebar | Playwright chat/camera suite проходит |
| P0-TESTS | В РАБОТЕ | Получить чистый полный pytest | полный suite должен завершаться exit 0 без failures/crash |
| P0-QUEUE | BLOCKER | Исправить ControlQueue manual takeover и STOP/reset coordinator latch | integration tests real Coordinator + fake Intiface bridge проходят |
| P0-PIPELINE | В РАБОТЕ | Сделать Operator единым side-effect execution path | side effects имеют fresh observation + Verification + TaskOutcome |
| P1-REMOVE | ОЖИДАЕТ | Проверить/fix `remove_pending` | production-path regression test |
| P1-TELEGRAM | ОЖИДАЕТ | Определить retry/backoff owner и закончить Telegram runtime | 429 retry test + real transport layer |
| P1-WIN-E2E | ОЖИДАЕТ | 10–20 реальных Windows Operator сценариев | Notepad/Calculator/Explorer/browser/multi-app с независимой проверкой |
| P1-BROWSER | ОЖИДАЕТ | Production hardening Browser Operator | SPA/modal/popup/new-tab/upload/download/redirect/stale refs |
| P1-AUTO | ОЖИДАЕТ | Universal Autonomous Runtime поверх Operator | OBSERVE → PLAN → ACT → VERIFY → RECOVER → CONTINUE |
| P1-SCREEN | ОЖИДАЕТ | Screen Intelligence | ROI + perceptual diff + debounce + semantic events + VLM fallback |
| P1-VOICE | ОЖИДАЕТ | Voice E2E на реальном железе | whisper → STT → Operator → Windows → Verify → TTS |
| P1-DORCH | ОЖИДАЕТ | Консолидация Dorch lifecycle | один ControlQueue/Coordinator, единый STOP/RESET/manual/remote/autonomous |
| P2-REMOTE | ОЖИДАЕТ | Remote/mobile E2E | phone → auth/session → action → verification → reconnect |
| P2-MEMORY | ОЖИДАЕТ | AgentContext как canonical runtime state | goal/mission/observations/events/recovery history без бесконечного transcript |
| P2-WEBUI | ОЖИДАЕТ | Модуляризация `webui/server.py` | handlers по подсистемам после стабилизации поведения |
| P2-PACK | ОЖИДАЕТ | Installer/portable | воспроизводимая установка runtime/models/voices/WebUI/Desktop/first-run checks |

## Правила выполнения

1. Сначала P0: тестовый baseline, ControlQueue lifecycle, единый execution/verification path.
2. Не добавлять параллельную новую архитектуру, если существующий Operator может решить задачу.
3. Не заявлять `СДЕЛАНО` без свежей проверки observable result.
4. Unit/mock подтверждает контракт, но не заменяет hardware/live E2E.
5. При параллельной работе агентов перед изменением файла: `git status` + diff файла; неизвестные dirty changes не откатывать.
