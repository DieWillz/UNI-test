# REPORT_007 — Lip-sync (D-17) статическая проверка

Дата: 2026-08-12 (ночь). Диспетчер: Hermes SOLO.

## Код (uni/desktop/renderer/avatar.js)
- `attachAudio(sourceNode)`:
  ```js
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  sourceNode.connect(analyser);   // подключаем TTS-аудио к анализатору
  ```
  ✅ Корректно: создаёт AnalyserNode и цепляет источник.
- `animate()` (цикл 30fps, D-18):
  ```js
  if (analyser && vrm.expressionManager) {
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);
    let sum = 0; for (let i...) sum += Math.abs(data[i]-128);
    const amp = Math.min(1, sum/data.length/40);
    vrm.expressionManager.setValue("aa", current==="speaking" ? amp : amp*0.1);
  }
  ```
  ✅ Читает амплитуду и ставит blend-shape `aa` (рот) пропорционально громкости.

## Важное ограничение (честно)
Lip-sync работает ТОЛЬКО если TTS-аудио реально идёт через Web Audio в браузере
и передаётся в `Avatar.attachAudio()`. В текущем MVP оверлея TTS триггерится через
`/api/tts`, но аудиопоток может не возвращаться в renderer как <audio>/MediaStream.
Поэтому полный визуальный proof lip-sync требует доработки передачи TTS-аудио в
браузер (отдельная задача). Код-уровень (AnalyserNode + setValue) корректен.

## Proof of work
- Статический разбор avatar.js: attachAudio + animate корректны (D-17 реализован кодом).
- node --check avatar.js: OK.
