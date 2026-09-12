# UNI Roadmap — 2026-09-10

Цель: довести существующую архитектуру UNI до состояния, где агент надёжно **видит → понимает → решает → действует → проверяет → исправляется → продолжает** без ложных success-статусов и постоянного ручного вмешательства.

## Phase 0 — Stabilize foundation

- [ ] Полный pytest = exit 0.
- [ ] ControlQueue manual takeover.
- [ ] STOP/reset ↔ Coordinator emergency latch.
- [ ] `remove_pending` regression.
- [ ] Integration tests с реальным Coordinator + fake Intiface bridge.
- [ ] Telegram retry/backoff contract.
- [ ] Mojibake cleanup.

DoD: полный suite завершается штатно; architecture audit 0/0; STOP → reset → new command работает; autonomous → manual takeover работает.

## Phase 1 — One execution pipeline

Свести side-effect paths к одному контракту:
`Task/Mission → ActionRegistry → Executor → fresh Observation → Verification → TaskOutcome`.

Мигрировать DirectCommand, `_free_form()`, VisualActionAgent и autonomous actions. Legacy не удалять до переноса call sites и тестов.

## Phase 2 — Real Windows Operator E2E

Проверить 10–20 сценариев: Notepad save, Calculator, Explorer filesystem, browser navigation, multi-app copy/paste, recovery при focus loss/overlay/moved element/stale refs.
## Phase 3 — Browser hardening

Live SPA/modal/popup/new-tab/download/upload/scroll/dynamic DOM/redirect/back-forward. Stale semantic references должны вызывать re-observe, а не слепой reuse.

## Phase 4 — Universal Autonomous Runtime

Канонический цикл: `OBSERVE → meaningful change? → PLAN/REPLAN → ACT → VERIFY → MEMORY → WAIT → OBSERVE`.
Добавить priority, cooldown, dedup, stuck detection, bounded retry, interruption, takeover/resume и recovery. Использовать существующий Operator.

## Phase 5 — Screen Intelligence

Perception hierarchy: **DOM/UIA → OCR → perceptual/region diff → VLM fallback**.
Добавить ROI, significance filter, debounce/cooldown, privacy filtering и semantic events.

## Phase 6 — Voice E2E

Реальный сценарий: тихая русская речь → faster-whisper → Operator → Windows → Verify → TTS. Проверить self-TTS suppression и interruption.

## Phase 7 — Dorch consolidation

Один ControlQueue + один Coordinator + единый STOP/RESET/manual/remote/pattern/autonomous status. Legacy `AutonomousSession` выводить только после миграции WebUI endpoints.

## Phase 8 — Remote + Telegram

Remote: phone/auth/session/action/verification/reconnect E2E. Telegram: закончить runtime transport, retry/backoff, media/STT и routing в Operator.
## Phase 9 — Memory and goal continuity

Использовать `AgentContext` как canonical runtime state: CurrentGoal, Mission, Completed/FailedSteps, RecentObservations, EnvironmentState, PendingEvents, UserPreferences и RecoveryHistory. Не хранить весь runtime только как бесконечный transcript.

## Phase 10 — WebUI cleanup

После стабилизации разделить `webui/server.py` на chat/operator/vision/speech/dorch/remote/launcher/settings/events handlers. Удалять legacy только после regression tests.

## Phase 11 — Packaging

Собрать воспроизводимый installer/portable с Python/runtime llama.cpp, моделями/конфигом, голосами, WebUI, Desktop и launcher. Добавить first-run диагностику GPU, audio, camera, LLM, STT и TTS.

## Уже реализованная база

- [x] Canonical contracts и evidence-based verification.
- [x] Action Registry.
- [x] Mission Planner.
- [x] Mission Executor.
- [x] Browser/Windows semantic providers.
- [x] Schema-driven WebUI editor `config.yaml`.
- [x] Архитектура perception с Vision как fallback, а не заменой OCR/DOM/UIA.

Главный принцип дальнейшей работы: **не переписывать UNI с нуля**. Сначала стабилизировать и свести существующие хорошие компоненты к единому execution/verification контуру, затем расширять E2E и упаковку.
