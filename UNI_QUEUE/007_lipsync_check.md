# Задача: Lip-sync (D-17) — проверка подключения AnalyserNode

## СЕКЦИЯ HERMES
avatar.js: Avatar.attachAudio(sourceNode) подключает AnalyserNode к TTS-аудио.
Проверь, что код корректен: attachAudio создаёт audioCtx + analyser, animate()
читает getByteTimeDomainData и ставит vrm.expressionManager.setValue('aa', amp).
Proof: статический разбор avatar.js + запись в `uni-hermes/outbox/REPORT_lipsync.md`.
(Полный визуальный proof требует, чтобы TTS-аудио шло в браузер — MVP через AnalyserNode.)
