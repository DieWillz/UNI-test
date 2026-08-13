# NOTES — что полезно из hermes-agent/ для Юни (выжимка)

> Папка-источник: `C:\LLM\UNI\agents\uni-hermes\hermes-agent\` — это **исходники
> самого Hermes Agent** (движка ИИ, которым управляет пользователь), НЕ проекта
> Юни. Юни живёт в `C:\LLM\UNI\uni`. Файлы здесь — **не готовый код Юни**,
> а переиспользуемые **паттерны**, очищенные от зависимостей Hermes.

## Прочитанные модули и вердикт

### tools/voice_mode.py (2308 строк) — ПОЛЕЗНО (высокая)
- Push-to-talk: запись sounddevice → WAV, STT-диспетчер, TTS-проигрывание.
- Паттерны, взятые в `voice_silence_detect.py` + `audio_env_detect.py`:
  - **Lazy audio import** — модуль не падает в headless (нет PortAudio).
  - **Silence-detection** — автостоп записи после N сек тишины (RMS-порог).
  - **detect_audio_environment** — честно определяет SSH/Docker/WSL/Termux и
    блокирует голос с понятной причиной (а не тихо падает).
- Юни уже делает микрофон/STT/TTS (`renderer/app.js` MediaRecorder→`/api/stt`,
  `uni/capabilities/speech.py` Piper/Silero). Паттерны применимы туда.

### tools/tts_streaming.py (488 строк) — ПОЛЕЗНО (средняя)
- Потоковый TTS по предложениям: `SentenceChunker` (режет LLM-дельты на
  предложения), `interruption latch` (прерывание речи при бардже),
  реестр провайдеров (ElevenLabs/OpenAI/Gemini/xAI).
- Взято в `tts_sentence_chunker.py`: `SentenceChunker` + `SpeechInterruptionLatch`.
- Провайдеры (ElevenLabs/OpenAI/...) — НЕ берём (Юни использует Silero/Piper,
  локально; внешние ключи не нужны).

### tools/patch_parser.py (637 строк) — НЕ ПОЛЕЗНО
- V4A-парсер патчей для Codex/Cline. Юни не патчит чужие PR → не нужно.

### agent/pet/render.py (682 строки) — НЕ ПОЛЕЗНО
- Рендер питомца в **терминале** (kitty/sixel/unicode escape-коды).
- Юни аватар — PNG в Electron (`renderer/`), не terminal-graphics.
  Механизм несовместим; оставляем как справку (как делается spritesheet-decode).

### gateway/shutdown_watchdog.py (457 строк) — ИДЕЯ (не копировать)
- OS-thread watchdog + heartbeat-файл для asyncio-шлюза Hermes.
- Юни launcher — node (`scripts/launcher.js`), не asyncio. Но **идея
  heartbeat-файла** (`gateway.heartbeat`) полезна для админки статусов —
  у Юни уже есть `/api/uni/status`; можно добавить файл-heartbeat для
  внешнего мониторинга «жив ли цикл, а не только процесс».

## Правило переноса
Модули Hermes завязаны на `hermes_constants`, `hermes_cli.config`, `tools.tts_tool`
и т.д. — копировать файлом **нельзя** (сломается). Берём только **логику**:
- `voice_silence_detect.py` — самостоятельный (sounddevice/numpy/wave).
- `tts_sentence_chunker.py` — самостоятельный (только re/time).
- `audio_env_detect.py` — самостоятельный (env + /proc).

Эти 3 файла не импортируют Hermes и готовы к адаптации в `uni/`.
