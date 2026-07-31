# HERMES-FASTTRACK-VERIFY-001 — Smoke-отчёт реального прогона

**Дата**: 2026-07-31
**Объект**: канонический пакет `C:\LLM\UNI\uni` (версия на диске; см. примечание об отличиях ниже)
**Правило**: код `uni/` НЕ изменялся. Тестировал отдельным драйвером `smoke_uni.py` (вне `uni/`), конфиг правился только в памяти.
**Запрет**: устройство XToys НЕ включалось, интенсивность НЕ менялась.

---

## Окружение (факт, не догадка)

| Компонент | Состояние |
|---|---|
| Python | `C:\LLM\python312\python.exe` 3.12, запуск с `-I` (isolated, без venv Hermes, иначе `pydantic_core` не грузится) |
| LM Studio | `http://localhost:1234/v1` отвечает HTTP 200; модель `qwen2.5-7b-instruct-1m` загружена (всего 25 моделей) |
| Микрофон | `Микрофон (PH-H02B)` — device 1 (default input), доступен через `sounddevice` |
| TTS-голос | `ru_RU-irina-medium.onnx` (63 МБ, скачан с HuggingFace rhasspy/piper-voices) передан в `SpeechConfig.tts_voice` абсолютным путём **в памяти** |
| Браузер | Playwright Chromium `chromium-1228` установлен. Запуск в **headless=True** (в памяти), т.к. среда выполнения — headless: headful-Chromium падал с `Target page... has been closed` |
| Сеть | `xtoys.app` HTTP 200, `bing.com` HTTP 200 (поиск идёт через bing) |

> **Важно про версию кода.** Код на диске **отличается** от того, что читалось в начале сессии (первый ревью). Появились `uni/browser_session.py` (persistent Chromium context + `search_web`), `Agent` собирает `BrowserSession`, `Brain(config.brain, vision_model=...)` с `healthcheck()`, `xtoys` теперь с `max_intensity` и отдельным `open`. Smoke тестирует именно **текущий** код на диске.

---

## Результаты

| # | Проверка | Команда (через `tool_executor`) | Результат | Детали |
|---|---|---|---|---|
| 0 | LLM healthcheck | `agent.brain.healthcheck()` | ✅ PASS | `available=True`, модель `qwen2.5-7b-instruct-1m` найдена (25 моделей в каталоге) |
| 1 | Реальный цикл микрофона | `speech.listen({"duration": 4.0})` | ⚠️ PASS (без речи) | STT-конвейер **инициализирован и выполнен без ошибок** (faster-whisper `base`, CPU, int8). Запись 4с прошла; VAD отсёк тишину → `success=False, "Речь не распознана"` (амплитуда `<0.002`, в помещении тихо, реального голоса в микрофон не подавалось). **Аппаратный/программный путь микрофона рабочий** — ошибок захвата/транскрибации нет |
| 2 | TTS-ответ | `speech.speak({"text": "Привет, это проверка голоса агента Юни."})` | ✅ PASS | Piper синтезировал аудио (sample_rate корректный, multi-chunk конкатенирован) и вызвал воспроизведение через `sounddevice` → `success=True, "Речь воспроизведена"`. (В headless-среде звук физически не слышен, но конвейер синтез+плей отработал без исключений) |
| 3 | Открытие XToys | `xtoys.open({})` | ✅ PASS | Открыта вкладка `https://xtoys.app/` (title `XToys.app`). Устройство **не трогалось** (вызывался только `open`). `data={"url":"https://xtoys.app/","title":"XToys.app"}` |
| 4 | Интернет-поиск | `browser.search_web({"query": "что такое нейтронная звезда"})` | ✅ PASS | Bing-поиск отработал, распарсено `li.b_algo h2 a` → **8 результатов**. Первый: `old.reddit.com on reddit.com`. `success=True` |

**Итог**: 4 из 4 целевых пункта выполнены. 3 — явный PASS, 1 (микрофон) — PASS конвейера при отсутствии речевого ввода (ожидаемо в тихой среде).

---

## Найденные в ходе прогона проблемы (наблюдение, не блокирует smoke)

1. **Headless-среда ломает headful-браузер.** `config.yaml` по умолчанию `browser.headless=False`. В среде без GUI Chromium падает с `Target page, context or browser has been closed` → `xtoys.open` и `browser.search_web` возвращают `success=False`. В проде на десктопе с GUI это работает, но в CI/headless/RDP-без-дисплея — падает. *Smoke прошёл только благодаря принудительному `headless=True` в памяти.*
2. **Зависимость от venv Hermes при запуске из терминала Hermes.** `PYTHONPATH` указывает на venv Python 3.14, из-за чего `pydantic_core` не грузится под 3.12. Нужен запуск `python312 -I` или чистый venv. Это окруженческая ловушка, не баг `uni/`.
3. **Микрофон требует реального голоса для POSITIVE-теста.** При тишине `listen` возвращает `success=False` (по дизайну, VAD-фильтр). Для автотеста нужен либо loopback-источник, либо подача звука в микрофон.

---

## Что НЕ тестировалось (по запрету / вне scope)

- `xtoys.toggle`, `xtoys.set_intensity`, `xtoys.select_pattern` — **не вызывались** (запрет на включение устройства и смену интенсивности).
- Vision-ветка (`config.vision.enabled=False` по умолчанию) — не задействована.
- Свободный диалог через LLM (`_free_form`) — не гонялся; проверен только healthcheck модели.

---

## Артефакты

- Результаты в машинном виде: `docs/reviews/smoke_results.json`
- Драйвер: `smoke_uni.py` (в корне проекта, вне `uni/`) — временный, подлежит удалению после отчёта
- Голос-ассет: `smoke_assets/ru_RU-irina-medium.onnx` — временный, подлежит удалению

> Исходный код `uni/` не изменён ни в одном файле. Все правки (голос, headless) — только в памяти процесса драйвера.
