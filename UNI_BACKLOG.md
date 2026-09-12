# UNI Backlog — 2026-09-10

Этот backlog заменяет устаревший список 2026-08-13. Приоритет — довести существующую архитектуру до надёжного автономного продукта, а не наращивать дублирующие подсистемы.

## P0 — стабилизация

- [ ] Полный `pytest` должен завершаться exit 0.
- [ ] Исправить ControlQueue manual takeover из autonomous режима.
- [ ] Исправить STOP → reset → new command с реальным emergency latch Coordinator.
- [ ] Проверить и при необходимости исправить `remove_pending`.
- [ ] Добавить integration tests `ControlQueue + ToyControlCoordinator + fake Intiface bridge`.
- [ ] Завершить Telegram retry/backoff contract.
- [ ] Устранить оставшийся mojibake в runtime/WebUI сообщениях.

## P0 — единый контур исполнения

- [ ] Свести DirectCommand, `_free_form()`, VisualActionAgent и Autonomous side effects к canonical Operator pipeline.
- [ ] Каждый side effect: ActionRegistry → execute → fresh observation → Verification → TaskOutcome.
- [ ] Не считать transport/action acknowledgement независимой проверкой результата.
- [ ] Legacy paths удалять только после миграции call sites и regression tests.

## P1 — perception

- [x] Зафиксирован порядок: DOM/UIA → OCR → visual diff → VLM/Vision fallback.
- [ ] Добавить significance threshold, ROI, debounce/cooldown для Screen Watch.
- [ ] Превращать изменения экрана в semantic events, а не слать каждый кадр в VLM.
- [ ] Добавить privacy/sensitive-region filtering для фонового наблюдения.
## P1 — Operator E2E

- [ ] Notepad: открыть → ввести текст → сохранить → проверить файл.
- [ ] Calculator: UIA interaction → проверить результат.
- [ ] Explorer: создать папку/файл → проверить filesystem state.
- [ ] Browser: navigate/find/click → проверить DOM/url/title/state.
- [ ] Multi-app copy/paste → проверить результат.
- [ ] Recovery: element moved/disappeared, overlay, focus loss, UIA unavailable, stale reference.

## P1 — автономность и голос

- [ ] Universal runtime: OBSERVE → meaningful event → PLAN/REPLAN → ACT → VERIFY → MEMORY → CONTINUE.
- [ ] Event priority, dedup, cooldown, stuck detection, bounded retry, user takeover/resume.
- [ ] Whisper/quiet speech E2E на реальном микрофоне.
- [ ] Исключить повторное распознавание собственного TTS.
- [ ] Проверить interruption: пользователь перебивает TTS новой командой.
## P1/P2 — интеграции и продукт

- [ ] Dorch: один lifecycle ControlQueue/Coordinator для manual/remote/pattern/autonomous/STOP.
- [ ] Remote/mobile: auth, reconnect, action routing, verification, phone E2E.
- [ ] Telegram: реальный transport runtime, media/STT, retry/backoff.
- [ ] AgentContext: current goal, mission, completed/failed steps, observations, pending events, recovery history.
- [ ] WebUI: после стабилизации разбить монолит `server.py` на handlers.
- [ ] Installer/portable + first-run diagnostics для GPU/audio/camera/LLM/STT/TTS.

## Уже закрыто в текущей итерации

- [x] Schema-driven админка `config.yaml`.
- [x] Secret masking / protected verification setting / atomic validated save.
- [x] Настройки основных capabilities доступны без ручного YAML.
- [x] Исправлен circular import modular handlers registry.
- [x] Исправлено перекрытие WebUI sidebar за счёт canonical `<main class="main">`.
- [x] Config/TTS/chat/camera targeted regression suite зелёный.
