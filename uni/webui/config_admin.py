"""Schema-driven, allowlisted editor for UNI's local ``config.yaml``.

The admin UI receives every user-relevant leaf setting, but secrets are
write-only and protected invariants are read-only. Updates are validated by the
canonical Pydantic ``Config`` model before an atomic file replacement.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from uni.config import Config, load_config

_GROUPS: list[tuple[str, str]] = [
    ("brain", "Модель и LLM"),
    ("capabilities.browser", "Браузер"),
    ("capabilities.computer", "Компьютер и ввод"),
    ("capabilities.camera", "Камера"),
    ("capabilities.speech", "Речь: STT / TTS"),
    ("capabilities.vision", "Зрение: OCR / Vision"),
    ("capabilities.xtoys", "Dorch / XToys"),
    ("agent", "Агент"),
    ("autonomous", "Автономность"),
    ("memory", "Память"),
    ("logging", "Логи"),
    ("council", "Council / провайдеры"),
    ("context", "Контекст"),
    ("demo", "Демо и диагностика"),
]

_READONLY = {"agent.verification_enabled"}
_SKIP_PREFIXES = ("agent.autonomous.",)
_SECRET_PARTS = ("api_key", "token", "secret", "password")

_RESTART_PREFIXES = (
    "brain.",
    "capabilities.browser.",
    "capabilities.computer.",
    "capabilities.camera.",
    "capabilities.speech.",
    "capabilities.vision.",
    "memory.path",
    "memory.max_dialogue_turns",
    "logging.directory",
)

_META: dict[str, dict[str, Any]] = {
    "brain.llm_provider": {"label": "LLM-провайдер", "options": ["embedded", "lmstudio"]},
    "brain.model": {"label": "Основная модель"},
    "brain.base_url": {"label": "LM Studio / внешний URL"},
    "brain.embedded_base_url": {"label": "Встроенный llama.cpp URL"},
    "brain.temperature": {"label": "Температура", "step": 0.05},
    "capabilities.speech.stt_device": {"label": "STT устройство", "options": ["cpu", "cuda", "auto"]},
    "capabilities.speech.stt_compute_type": {"label": "STT тип вычислений", "options": ["int8", "float16", "float32"]},
    "capabilities.speech.tts_provider": {
        "label": "TTS-провайдер",
        "options": ["silero", "piper", "browser", "xtts", "fish"],
        "description": "Выбирает движок, которым Юни озвучивает ответы. После смены нужно перезапустить речевой модуль.",
    },
    "capabilities.speech.silero_speaker": {
        "label": "Голос Silero",
        "options": ["xenia", "kseniya", "baya", "eugene", "aidar"],
        "description": "Голос для Silero. Используется, когда TTS-провайдер установлен в silero.",
    },
    "capabilities.speech.tts_voice": {
        "label": "Голос Piper",
        "options": ["ru_RU-irina-medium.onnx"],
        "description": "Голосовая модель Piper. Используется, когда TTS-провайдер установлен в piper.",
    },
    "capabilities.vision.provider": {"label": "Vision-провайдер", "options": ["openai", "gradio", "moondream_cpp"]},
    "capabilities.vision.tier0_uia_enabled": {"label": "Tier-0: UIA"},
    "capabilities.vision.tier0_ocr_enabled": {"label": "Tier-0: OCR"},
    "capabilities.vision.tier0_dom_enabled": {"label": "Tier-0: DOM"},
    "capabilities.vision.tier1_verify_enabled": {"label": "Tier-1: визуальная проверка"},
    "capabilities.vision.local_fallback_enabled": {"label": "Локальный fallback"},
    "capabilities.xtoys.max_intensity": {"label": "Жёсткий лимит мощности, %"},
    "capabilities.xtoys.autonomous_physical": {"label": "Разрешить автономное управление устройством"},
    "agent.input_mode": {"label": "Режим ввода", "options": ["text", "voice", "mixed"]},
    "autonomous.enabled": {"label": "Автономный режим"},
    "autonomous.auto_start_session": {"label": "Автозапуск автономной сессии"},
    "context.tonal_mode": {"label": "Тон контекста", "options": ["playful", "spicy", "custom"]},
}

_LABELS = {
    "enabled": "Включено", "model": "Модель", "api_key": "API key",
    "base_url": "Base URL", "timeout_seconds": "Таймаут, сек",
    "max_tokens": "Макс. токенов", "headless": "Headless",
    "device_index": "Номер устройства", "width": "Ширина", "height": "Высота",
    "sample_rate": "Частота, Гц", "input_device": "Устройство ввода",
    "output_device": "Устройство вывода", "microphone_gain": "Усиление микрофона",
    "voice_activation_threshold": "Порог активации голоса",
    "voice_silence_seconds": "Пауза завершения фразы, сек",
    "max_utterance_seconds": "Макс. длина фразы, сек",
    "max_context_tokens": "Контекст памяти, токенов",
    "max_dialogue_turns": "Хранимых реплик", "directory": "Каталог",
}

_PATH_DESCRIPTIONS = {
    "brain.llm_provider": "Определяет, откуда Юни получает ответы модели: из встроенного llama.cpp или из LM Studio.",
    "brain.model": "Основная текстовая модель Юни. Смена влияет на качество, скорость и потребление памяти.",
    "brain.vision_model": "Модель, которой Юни передаёт изображения и скриншоты для визуального анализа.",
    "brain.base_url": "Адрес OpenAI-совместимого API LM Studio или другого внешнего сервера модели.",
    "brain.embedded_base_url": "Адрес встроенного llama.cpp, когда выбран встроенный LLM-провайдер.",
    "brain.temperature": "Управляет вариативностью ответов: ниже — стабильнее и строже, выше — свободнее и разнообразнее.",
    "brain.max_tokens": "Ограничивает максимальную длину одного ответа модели. Большее значение может увеличить задержку и расход памяти.",
    "capabilities.speech.microphone_gain": "Усиливает вход микрофона перед распознаванием речи. Повышайте, если Юни плохо слышит тихую речь.",
    "capabilities.speech.voice_activation_threshold": "Минимальная громкость, с которой Юни считает, что вы начали говорить. Слишком низкое значение ловит шум.",
    "capabilities.speech.voice_silence_seconds": "Сколько тишины ждать перед завершением голосовой фразы. Больше — меньше обрывов, но выше задержка.",
    "capabilities.speech.max_utterance_seconds": "Максимальная длительность одной распознаваемой голосовой фразы.",
    "capabilities.speech.stt_model": "Модель распознавания речи. Более крупная обычно точнее, но требует больше ресурсов.",
    "capabilities.speech.stt_device": "Устройство, на котором работает распознавание речи: CPU, GPU или автоматический выбор.",
    "capabilities.speech.stt_compute_type": "Точность вычислений STT. Более лёгкий тип экономит ресурсы, более точный может быть медленнее.",
    "capabilities.vision.local_fallback_enabled": "Разрешает локальные UIA/OCR fallback-механизмы, когда основной визуальный путь недоступен.",
    "capabilities.xtoys.max_intensity": "Жёстко ограничивает максимальную мощность устройства независимо от команды Юни.",
    "agent.input_mode": "Определяет, принимает ли Юни текст, голос или оба типа ввода.",
    "autonomous.enabled": "Включает автономную работу Юни без постоянных ручных команд пользователя.",
    "memory.max_dialogue_turns": "Сколько последних реплик диалога сохранять в активном контексте Юни.",
}

_PATH_DESCRIPTIONS.update({
    "brain.api_key": "Ключ авторизации для LLM API. Для локального LM Studio обычно не важен, но нужен внешнему серверу, если тот проверяет Bearer-токен.",
    "brain.vision_base_url": "Отдельный адрес API для анализа изображений. Если пусто, Vision использует основной LLM endpoint.",
    "brain.vision_api_key": "Отдельный ключ авторизации для Vision API, если сервер изображений требует свой токен.",
    "brain.timeout_seconds": "Максимальное время ожидания ответа LLM. После этого запрос считается зависшим и завершается ошибкой.",
    "capabilities.browser.headless": "Определяет, будет ли браузер Юни виден на экране. Выключено — действия происходят в обычном видимом Chrome.",
    "capabilities.browser.viewport_width": "Ширина окна браузера, под которую рассчитываются координаты, DOM и скриншоты.",
    "capabilities.browser.viewport_height": "Высота окна браузера, под которую рассчитываются координаты, DOM и скриншоты.",
    "capabilities.browser.channel": "Какой установленный браузер запускает Playwright, например Chrome. Влияет на профиль, совместимость и видимое окно.",
    "capabilities.browser.user_data_dir": "Папка профиля браузера Юни. Здесь сохраняются cookies, авторизации и настройки сайтов.",
    "capabilities.browser.search_engine": "Шаблон адреса, который Юни использует для обычного веб-поиска.",
    "capabilities.browser.image_search_engine": "Шаблон адреса, который Юни использует при поиске изображений.",
    "capabilities.browser.cdp_url": "Адрес Chrome DevTools Protocol для подключения к уже запущенному браузеру вместо запуска нового.",
    "capabilities.browser.agent_cursor.enabled": "Показывает отдельный визуальный курсор Юни во время автоматических действий, чтобы было видно, куда она собирается нажать.",
    "capabilities.browser.agent_cursor.label": "Текст рядом с визуальным курсором агента во время действий в браузере.",
    "capabilities.browser.agent_cursor.move_ms": "Длительность анимации перемещения визуального курсора Юни между точками.",
    "capabilities.browser.agent_cursor.hide_after_ms": "Через сколько миллисекунд без действий скрывать визуальный курсор Юни.",
    "capabilities.computer.use_uia": "Разрешает сначала искать элементы Windows через UI Automation. Это точнее координат и обычно надёжнее OCR.",
    "capabilities.computer.failsafe": "Включает аварийную защиту компьютерного управления, чтобы неконтролируемое движение мыши можно было остановить.",
    "capabilities.computer.mouse_move_duration": "Сколько секунд Юни ведёт мышь к целевой точке. Больше — движение заметнее и плавнее; меньше — быстрее.",
    "capabilities.computer.action_badge": "Показывает на экране индикатор, когда Юни выполняет действие мышью или клавиатурой.",
    "capabilities.computer.action_badge_label": "Текст на индикаторе действий компьютера, чтобы отличать действия Юни от действий пользователя.",
    "capabilities.camera.enabled": "Разрешает Юни использовать камеру. Выключение полностью блокирует захват кадров камерой.",
    "capabilities.camera.device_index": "Номер камеры в Windows. Меняйте, если Юни открывает не ту веб-камеру.",
    "capabilities.camera.backend": "Способ подключения OpenCV к камере. На Windows dshow обычно уменьшает задержки и проблемы выбора устройства.",
    "capabilities.camera.width": "Разрешение кадра камеры по ширине. Выше — больше деталей, но больше нагрузка.",
    "capabilities.camera.height": "Разрешение кадра камеры по высоте. Выше — больше деталей, но больше нагрузка.",
    "capabilities.camera.min_brightness": "Ниже этой средней яркости кадр считается слишком тёмным для надёжного анализа.",
})
_PATH_DESCRIPTIONS.update({
    "capabilities.camera.sample_interval_seconds": "Как часто автономное наблюдение может брать очередной кадр с камеры. Меньше — реакция быстрее, но выше нагрузка.",
    "capabilities.camera.reminder_interval_seconds": "Через какой интервал повторять напоминание, если камера используется для длительного наблюдения.",
    "capabilities.camera.default_watch_seconds": "Стандартная длительность одной сессии наблюдения камерой, если пользователь не указал время явно.",
    "capabilities.camera.max_watch_seconds": "Жёсткий предел длительности одной сессии наблюдения камерой, чтобы она не оставалась включённой бесконечно.",
    "capabilities.speech.stt_beam_size": "Сколько вариантов распознавания Whisper сравнивает перед выбором текста. Больше может повысить точность, но замедляет распознавание.",
    "capabilities.speech.tts_provider": "Выбирает движок, которым Юни озвучивает ответы: Silero, Piper или другой подключённый TTS.",
    "capabilities.speech.tts_voice": "Выбирает файл голоса Piper. На Silero этот параметр не влияет.",
    "capabilities.speech.silero_model": "Версия русской модели Silero TTS, которая генерирует голос. Смена модели может изменить набор доступных голосов и качество речи.",
    "capabilities.speech.silero_speaker": "Выбирает конкретный голос Silero, которым Юни говорит: например Xenia или Kseniya.",
    "capabilities.speech.silero_sample_rate": "Частота аудио, которую генерирует Silero. Неверное значение может менять скорость/качество или ломать воспроизведение.",
    "capabilities.speech.sample_rate": "Частота входного аудио для распознавания речи. Должна быть совместима с микрофоном и STT pipeline.",
    "capabilities.speech.listen_duration": "Длина одного короткого окна прослушивания микрофона. Больше — Юни реже опрашивает микрофон, но захватывает более длинный фрагмент.",
    "capabilities.speech.input_device": "Номер микрофона Windows, с которого Юни слушает речь. Меняйте, если выбран не тот микрофон.",
    "capabilities.speech.output_device": "Номер аудиоустройства Windows, через которое Юни воспроизводит голос.",
    "capabilities.speech.use_chunker": "Разбивает длинный текст на фразы перед озвучкой. Включение уменьшает задержку до начала речи и снижает риск обрыва длинного TTS.",
    "capabilities.vision.enabled": "Разрешает визуальный анализ скриншотов и изображений. Если выключить, Юни сможет использовать DOM/UIA/OCR, но не VLM-анализ картинки.",
    "capabilities.vision.provider": "Определяет протокол, через который Юни отправляет изображения модели: OpenAI-compatible API, Gradio или moondream.cpp.",
    "capabilities.vision.model": "Имя модели внутри Vision capability. Значение auto позволяет backend выбрать подходящую доступную мультимодальную модель.",
    "capabilities.vision.gradio_url": "Адрес локального Gradio-сервера Vision, если выбран Gradio-провайдер.",
    "capabilities.vision.gradio_api_name": "Основной Gradio endpoint, через который отправляется изображение и вопрос к нему.",
    "capabilities.vision.gradio_fallback_api_name": "Резервный Gradio endpoint, который пробуется, если основной endpoint недоступен.",
    "capabilities.vision.moondream_url": "Адрес отдельного Moondream/VLM сервера, если он используется вместо основного LLM endpoint.",
    "capabilities.vision.resize_width": "До какой ширины уменьшать скриншот перед отправкой VLM. Меньше — быстрее, но теряются мелкие детали.",
    "capabilities.vision.resize_height": "До какой высоты уменьшать скриншот перед отправкой VLM. Меньше — быстрее, но теряются мелкие детали.",
    "capabilities.vision.save_screenshots": "Если включено, сохраняет обработанные кадры на диск для диагностики; если выключено — кадры остаются только в памяти.",
    "capabilities.vision.local_fallback_enabled": "Разрешает локальный резервный визуальный путь, когда основной Vision backend не отвечает.",
})
_PATH_DESCRIPTIONS.update({
    "capabilities.vision.tier0_uia_enabled": "Разрешает искать элементы интерфейса Windows через UI Automation до обращения к Vision-модели.",
    "capabilities.vision.tier0_ocr_enabled": "Разрешает читать текст на экране через OCR до обращения к Vision-модели.",
    "capabilities.vision.tier0_dom_enabled": "Разрешает использовать DOM браузера для поиска элементов страницы до визуального распознавания.",
    "capabilities.vision.tier1_verify_enabled": "После действия делает визуальную проверку результата, чтобы Юни не считала задачу выполненной только потому, что клик был отправлен.",
    "capabilities.vision.tier1_verify_delay": "Пауза после действия перед контрольным снимком экрана. Нужна, чтобы интерфейс успел обновиться.",
    "capabilities.vision.tier1_diff_threshold": "Минимальная заметная разница между кадрами для признания экрана изменившимся после действия.",
    "capabilities.vision.tier2_min_vram_gb": "Минимальный объём свободной VRAM, при котором разрешается более тяжёлый визуальный уровень.",
    "capabilities.xtoys.url": "Адрес XToys, который используется интеграцией Dorch для удалённых/веб-сценариев.",
    "capabilities.xtoys.autonomous_physical": "Разрешает автономному режиму Юни самой отправлять команды физическому устройству без отдельной команды на каждый шаг.",
    "agent.default_role": "Роль, с которой Юни стартует по умолчанию и которая определяет её инструкции и стиль поведения.",
    "agent.cycle_interval": "Пауза между основными итерациями agent loop. Меньше — Юни чаще проверяет состояние, но сильнее нагружает систему.",
    "agent.max_retries": "Сколько раз Юни повторяет неудачный шаг до того, как признает его ошибкой и сменит стратегию/остановится.",
    "agent.verification_enabled": "Требует отдельной проверки результата после действий. Защищённая настройка: UI не позволяет отключить её.",
    "agent.input_mode": "Определяет, принимает ли основной агент текст, голос или оба источника команд одновременно.",
    "agent.speak_responses": "Если включено, текстовые ответы Юни автоматически отправляются ещё и в TTS для озвучивания.",
    "agent.max_parallel_tasks": "Сколько задач Юни может выполнять одновременно. Большое значение повышает параллелизм, но увеличивает конкуренцию за CPU/GPU и интерфейс.",
    "agent.max_pending_tasks": "Максимальная очередь ещё не запущенных задач. Новые задачи сверх лимита не должны бесконтрольно накапливаться.",
    "agent.task_timeout_seconds": "Максимальное время выполнения одной задачи до принудительного таймаута.",
    "agent.exploration_steps": "Сколько исследовательских шагов разрешено сделать перед тем, как Юни должна перейти к более определённому плану действий.",
    "agent.visual_ui_max_steps": "Максимальное число шагов мышью/клавиатурой в одном визуальном UI-сценарии, чтобы агент не зацикливался.",
    "agent.response_max_chars": "Ограничивает длину обычного текстового ответа Юни в интерфейсе.",
    "agent.spoken_response_max_chars": "Ограничивает длину текста, который отправляется в TTS, чтобы голосовые ответы не становились слишком длинными.",
    "autonomous.enabled": "Разрешает автономный режим вообще. Если выключено, фоновые автономные циклы не должны запускаться даже по запросу автосессии.",
    "autonomous.auto_start_session": "Если включено, при запуске UNI автономная сессия стартует сама без отдельной команды. Если выключено, автономность доступна, но запускать её нужно явно.",
    "autonomous.vision_interval_seconds": "Как часто автономный цикл повторно анализирует экран. Меньше — быстрее замечает изменения, но чаще вызывает Vision.",
    "autonomous.speech_interval_seconds": "Как часто автономный цикл проверяет голосовой канал/возможность сказать следующую фразу.",
})
_PATH_DESCRIPTIONS.update({
    "autonomous.device_interval_seconds": "Как часто автономный цикл проверяет состояние подключённых устройств и возможность выполнить физическое действие.",
    "autonomous.conductor_interval_seconds": "Интервал работы автономного координатора, который пересматривает текущий план и следующие действия.",
    "autonomous.enable_device_motion": "Разрешает автономному режиму использовать движения/сигналы устройств как вход для поведения и реакций.",
    "autonomous.require_connect": "Если включено, автономная сессия не стартует без обязательного подключения нужного внешнего устройства/сервиса.",
    "memory.path": "Файл рабочей памяти Юни. В нём сохраняется контекст, который должен переживать перезапуск процесса.",
    "memory.max_context_tokens": "Сколько токенов памяти можно подмешать в один запрос к модели. Больше — больше контекста, но меньше места остаётся под текущий диалог и ответ.",
    "memory.max_dialogue_turns": "Сколько последних реплик диалога хранить в рабочей памяти для продолжения разговора.",
    "logging.enabled": "Включает запись технических логов UNI. Если выключить, диагностировать ошибки после факта будет значительно сложнее.",
    "logging.directory": "Папка, куда UNI пишет runtime-логи и диагностические файлы.",
    "council.enabled": "Разрешает режим Council, где несколько моделей/провайдеров могут независимо предложить решения для одной задачи.",
    "council.artifacts_dir": "Папка, куда сохраняются результаты, ответы и артефакты раундов Council.",
    "council.concurrency": "Сколько участников Council можно опрашивать одновременно. Больше — быстрее раунд, но выше нагрузка и число параллельных запросов.",
    "council.timeout_seconds": "Сколько секунд ждать отдельного участника Council до признания его ответа просроченным.",
    "council.collect_signatures": "Сохраняет подписи/идентификаторы участников вместе с ответами, чтобы было видно, какая модель дала конкретное мнение.",
    "council.browser_enabled": "Разрешает Council использовать браузерные источники, если для решения задачи нужна внешняя информация.",
    "council.inform_tos": "Требует учитывать/показывать ограничения условий использования провайдеров при подключении внешних сервисов.",
    "council.free_tier_only": "Ограничивает Council только бесплатными моделями/тарифами, чтобы случайно не запускать платные запросы.",
    "council.min_interval_seconds": "Минимальная пауза между запросами Council к провайдерам для ограничения частоты и риска rate limit.",
    "council.browser_profile": "Отдельный профиль браузера Council, где хранятся его cookies и авторизации, не смешиваясь с основным браузером Юни.",
    "council.api_endpoints.openrouter.base_url": "API-адрес OpenRouter, через который Council отправляет запросы к выбранной внешней модели.",
    "council.api_endpoints.openrouter.model": "Конкретная модель OpenRouter, которую Council использует на этом endpoint.",
    "council.api_endpoints.openrouter.api_key": "Ключ OpenRouter для запросов Council. Без него платные/авторизованные модели OpenRouter недоступны.",
    "context.enabled": "Включает дополнительный контекстный слой, который может подмешивать внешние источники/фиды в запросы Юни.",
    "context.allow_external_scrape": "Разрешает контекстному слою собирать данные со внешних страниц, а не только использовать локальные источники.",
    "context.injection_rate": "Доля/частота, с которой дополнительный контекст подмешивается в диалог. Меньше — реже влияет на ответы Юни.",
    "context.feeds": "Список источников дополнительного контекста, которые Юни может читать при включённом context layer.",
})
_PATH_DESCRIPTIONS.update({
    "context.tonal_mode": "Выбирает общий тон дополнительного контекста, который может влиять на формулировки Юни при включённом context layer.",
    "demo.xtoys.url": "Адрес XToys, который используется только в демонстрационных сценариях и не меняет основной Dorch endpoint.",
    "demo.xtoys.wander_seconds": "Сколько секунд длится один демонстрационный цикл случайного/плавного изменения поведения XToys.",
    "demo.xtoys.pet_points": "Сколько контрольных точек используется в демонстрационной траектории XToys; больше — движение разнообразнее.",
    "demo.mouse.label_text": "Подпись рядом с демонстрационным курсором, чтобы на экране было видно, что двигается именно Юни.",
    "demo.mouse.speed": "Скорость демонстрационного перемещения курсора. Больше — быстрее проходит траекторию.",
    "demo.mouse.fps": "Частота обновления демонстрационной анимации мыши. Больше — плавнее, но немного выше нагрузка.",
    "demo.mouse.failsafe": "Оставляет аварийную остановку активной во время демонстрационного управления мышью.",
})

_LEAF_DESCRIPTIONS = {
    "enabled": "Включает или выключает эту возможность.",
    "api_key": "Ключ доступа к сервису. Значение скрывается в интерфейсе и заменяется только при вводе нового.",
    "timeout_seconds": "Сколько секунд ждать ответ сервиса до ошибки по таймауту.",
    "headless": "Если включено, браузер работает без видимого окна; если выключено — окно браузера видно пользователю.",
    "device_index": "Номер физического устройства, которое будет использовать Юни.",
    "width": "Рабочая ширина изображения или области захвата.",
    "height": "Рабочая высота изображения или области захвата.",
    "sample_rate": "Частота обработки аудио. Меняет совместимость и качество звукового потока.",
    "input_device": "Устройство, с которого Юни получает звук.",
    "output_device": "Устройство, через которое Юни воспроизводит звук.",
    "directory": "Папка, куда Юни сохраняет данные этого раздела.",
}


def _is_secret(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1].casefold()
    # Token budgets are public numeric settings, not authentication tokens.
    if leaf in {"max_tokens", "max_context_tokens"}:
        return False
    return any(part in leaf for part in _SECRET_PARTS)


def _group_for(path: str) -> tuple[int, str]:
    best: tuple[int, str] | None = None
    for index, (prefix, title) in enumerate(_GROUPS):
        if path == prefix or path.startswith(prefix + "."):
            if best is None or len(prefix) > len(_GROUPS[best[0]][0]):
                best = (index, title)
    return best or (len(_GROUPS), "Прочее")


def _iter_leaves(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _iter_leaves(child, path)
        return
    yield prefix, value


def _label_for(path: str) -> str:
    meta = _META.get(path) or {}
    if meta.get("label"):
        return str(meta["label"])
    leaf = path.rsplit(".", 1)[-1]
    return _LABELS.get(leaf, leaf.replace("_", " ").capitalize())


def _description_for(path: str) -> str:
    meta = _META.get(path) or {}
    if meta.get("description"):
        return str(meta["description"])
    if path in _PATH_DESCRIPTIONS:
        return _PATH_DESCRIPTIONS[path]
    leaf = path.rsplit(".", 1)[-1]
    if leaf in _LEAF_DESCRIPTIONS:
        return _LEAF_DESCRIPTIONS[leaf]
    return (
        "Для этого нового технического параметра ещё нет проверенного пользовательского описания. "
        "Не меняйте его вслепую; ориентируйтесь на техническое имя ниже."
    )


def _field_kind(path: str, value: Any) -> str:
    if _is_secret(path):
        return "password"
    if (meta := _META.get(path)) and meta.get("options"):
        return "select"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, list):
        return "list"
    return "text"


def _field_descriptor(path: str, value: Any) -> dict[str, Any]:
    meta = dict(_META.get(path) or {})
    secret = _is_secret(path)
    descriptor: dict[str, Any] = {
        "path": path,
        "label": _label_for(path),
        "kind": _field_kind(path, value),
        "value": "" if secret else value,
        "secret": secret,
        "secret_set": bool(value) if secret else False,
        "readonly": path in _READONLY,
        "restart_required": path.startswith(_RESTART_PREFIXES),
        "description": _description_for(path),
    }
    for key in ("options", "min", "max", "step"):
        if key in meta:
            descriptor[key] = meta[key]
    return descriptor


def build_admin_config_snapshot(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    cfg = load_config(str(config_path))
    dumped = cfg.model_dump(mode="python")
    grouped: dict[int, list[dict[str, Any]]] = {}
    titles: dict[int, str] = {}
    for field_path, value in _iter_leaves(dumped):
        if any(field_path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            continue
        index, title = _group_for(field_path)
        grouped.setdefault(index, []).append(_field_descriptor(field_path, value))
        titles[index] = title
    groups = [
        {"id": str(index), "title": titles[index], "fields": grouped[index]}
        for index in sorted(grouped)
    ]
    return {"groups": groups, "config_path": str(config_path), "version": 1}


def _get_child(container: Any, key: str) -> Any:
    return container[key] if isinstance(container, dict) else getattr(container, key)


def _set_child(container: Any, key: str, value: Any) -> None:
    if isinstance(container, dict):
        container[key] = value
    else:
        setattr(container, key, value)


def _set_path(container: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    current = container
    for key in parts[:-1]:
        current = _get_child(current, key)
    _set_child(current, parts[-1], value)


def _get_path(container: Any, path: str) -> Any:
    current = container
    for key in path.split("."):
        current = _get_child(current, key)
    return current


def _editable_paths(cfg: Config) -> set[str]:
    return {
        path
        for path, _value in _iter_leaves(cfg.model_dump(mode="python"))
        if not any(path.startswith(prefix) for prefix in _SKIP_PREFIXES)
    }


def _set_mapping_path(container: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: dict[str, Any] = container
    for key in parts[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[parts[-1]] = value


def _write_config_safely(config_path: Path, serialized: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    last_error: PermissionError | None = None
    for _attempt in range(4):
        try:
            os.replace(tmp_path, config_path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.08)
    original = config_path.read_bytes() if config_path.exists() else b""
    backup = config_path.with_suffix(config_path.suffix + ".save-backup")
    backup.write_bytes(original)
    try:
        data = tmp_path.read_bytes()
        with config_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if config_path.read_bytes() != data:
            raise OSError("config write verification failed")
        tmp_path.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
    except Exception:
        try:
            config_path.write_bytes(original)
        except OSError:
            pass
        raise last_error or PermissionError("config replacement failed")


def apply_admin_config_updates(path: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(updates, dict):
        raise ValueError("updates must be an object")

    config_path = Path(path).resolve()
    current = load_config(str(config_path))
    editable = _editable_paths(current)
    data = current.model_dump(mode="python")
    changed: list[str] = []

    for field_path, value in updates.items():
        if field_path not in editable:
            raise ValueError(f"unknown config field: {field_path}")
        if field_path in _READONLY:
            raise ValueError(f"read-only config field: {field_path}")
        if _is_secret(field_path) and value == "":
            continue
        if _get_path(data, field_path) != value:
            _set_path(data, field_path, value)
            changed.append(field_path)

    try:
        validated = Config.model_validate(data)
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors(include_url=False)[:8]
        )
        raise ValueError(f"invalid config update: {detail}") from exc

    if not changed:
        return {"changed": [], "restart_required": [], "saved": False}

    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError("config root must be an object")
    for field_path in changed:
        _set_mapping_path(raw_data, field_path, _get_path(validated, field_path))
    serialized = yaml.safe_dump(raw_data, allow_unicode=True, sort_keys=False)
    _write_config_safely(config_path, serialized)

    # Keep the cached Config object and its nested model identities alive where
    # possible: running components may hold references to those nested models.
    for field_path in changed:
        _set_path(current, field_path, _get_path(validated, field_path))

    restart = sorted(
        field_path for field_path in changed
        if field_path.startswith(_RESTART_PREFIXES)
    )
    return {
        "changed": sorted(changed),
        "restart_required": restart,
        "saved": True,
    }
