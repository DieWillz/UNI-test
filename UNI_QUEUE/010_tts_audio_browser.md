# Задача 010: Передача TTS-аудио в браузер (для lip-sync D-17)

## СЕКЦИЯ HERMES
Lip-sync (avatar.js attachAudio+animate) корректен, но требует, чтобы TTS-аудио
реально шло через Web Audio в renderer. Сейчас /api/tts триггерит озвучку, но
аудиопоток может не возвращаться в браузер как <audio>/MediaStream.
Нужно: либо вернуть audio_url из /api/tts и проиграть через Audio()+attachAudio,
либо использовать SpeechSynthesis (уже есть) + AnalyserNode на нём.
Proof: аватар открывает рот синхронно с речью.
