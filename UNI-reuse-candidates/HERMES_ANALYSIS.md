# HERMES_ANALYSIS — Заключение Hermes по папке hermes-agent/

> Автор: Hermes (Гермес), агент-координатор Юни. Дата: 2026-08-13.
> Назначение: пользователь попросил проанализировать
> `C:\LLM\UNI\agents\uni-hermes\hermes-agent\` на полезное для Юни и сложить
> отдельно для анализа другими ИИ.

## 1. Что это за папка

`hermes-agent/` — **исходный код самого Hermes Agent** (личного ИИ-движка
пользователя: CLI, gateway для Telegram/Discord/Slack, TUI, Electron-десктоп,
плагины, cron, навыки). Это НЕ код проекта Юни. Юни — отдельный проект
(`C:\LLM\UNI\uni`, локальный Windows AI-оператор: чат/голос/браузер/зрение/
камера/роли/автономность/XToys).

Следовательно, содержимое `hermes-agent/` **не является готовым кодом Юни** —
это движок, которым я (Hermes) управляю. Но в нём есть **зрелые паттерны**,
которые Юни может переиспользовать (голос, TTS, детект окружения).

## 2. Что полезно (и сложено в эту папку)

| Модуль Hermes | Польза | Сложено как |
|---|---|---|
| `tools/voice_mode.py` | Высокая — silence-detection, lazy audio, env-detect | `voice_silence_detect.py`, `audio_env_detect.py` |
| `tools/tts_streaming.py` | Средняя — SentenceChunker, interruption latch | `tts_sentence_chunker.py` |
| `tools/patch_parser.py` | Нет — V4A-патчи не нужны Юни | — |
| `agent/pet/render.py` | Нет — terminal-graphics, не Electron | — |
| `gateway/shutdown_watchdog.py` | Идея — heartbeat-файл для статусов | (заметка в NOTES.md) |

## 3. Что НЕ стоит копировать

- **Сырые файлы Hermes** — завязаны на `hermes_constants`, `hermes_cli.config`,
  `tools.tts_tool`, `hermes_logging` и т.д. Копирование файлом сломается.
- **`patch_parser.py`** — Юни не патчит чужие PR.
- **`pet/render.py`** — терминальный спрайт-рендер; Юни аватар = PNG в Electron.
- **`shutdown_watchdog.py`** — привязан к asyncio-шлюзу Hermes; у Юни node-launcher.

## 4. Рекомендация для других ИИ (анализаторов)

1. Читать **3 самостоятельных файла** в этой папке (`voice_silence_detect.py`,
   `tts_sentence_chunker.py`, `audio_env_detect.py`) — они очищены от зависимостей
   Hermes и готовы к адаптации в `uni/capabilities/speech.py`.
2. `NOTES.md` — выжимка по каждому прочитанному модулю (что взято / почему нет).
3. Паттерны для переноса в Юни:
   - **Silence-detection** в микрофон (автостоп записи) → `speech.py`.
   - **SentenceChunker + interruption latch** → conversational TTS (говорить
     по предложениям, прерывать при бардже) → `speech.py`.
   - **detect_audio_environment** → честный статус «микрофон недоступен» в UI.
4. НЕ предлагать импорт `hermes_*` модулей в Юни — это архитектурная ошибка.

## 5. Статус

- Сложено: 3 самостоятельных .py + NOTES.md + этот файл.
- Lint: все 3 .py проходят `node --check`? Нет — это Python; `python -c "import ast; ast.parse(...)"` чисто (проверено в терминале Hermes: lint OK).
- Не закоммичено (пользователь решит, куда класть; папка `UNI-reuse-candidates/`
  вне канона `uni/`, но в репо `C:\LLM\UNI` — можно запушить как справку).

Hermes = Гермес, агент-координатор Юни. Подпись: 2026-08-13.
