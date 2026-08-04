# UNI Control Panel

Локальная веб-панель: очередь задач, создание поручений, run через Development Coordinator, заметки координатора.

## Запуск

```bash
cd uni_panel
pip install -r requirements.txt
python app.py
```

Открой в браузере: **http://127.0.0.1:8787**

Windows:

```bat
start-panel.bat
```

## Куда положить

**Вариант A (полная интеграция):** скопируй папку `uni_panel` в **корень** репозитория [UNI-test](https://github.com/DieWillz/UNI-test) (рядом с `uni/`, `scripts/`, `.uni-dev/`).

Тогда панель подхватит `uni.devcoord` и будет создавать/запускать настоящие задачи координатора.

**Вариант B:** запуск из `artifacts` — работает на **локальном JSON-хранилище** (задачи сохраняются, run не ходит в LLM, пока нет devcoord).

## Возможности

- Статус: workspace, devcoord ON/OFF, провайдеры
- Создать задачу (title, goal, instructions, providers, files)
- Список / детали / **Run**
- Лента событий
- Локальные заметки координатора

Ответы моделей остаются **proposals** — код сами не правят (как в ADR-0009).

## Порт

По умолчанию `8787`. Смена: в конце `app.py` у `uvicorn.run(...)`.
