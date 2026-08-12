# GITHUB_LINK — актуальное состояние проекта (2026-08-12)

## Репозиторий
- **URL:** https://github.com/DieWillz/UNI-test
- **Видимость:** PUBLIC (доступен всем без инвайтов/токенов — ревьюеры просто открывают ссылку)
- **Рабочая ветка:** https://github.com/DieWillz/UNI-test/tree/night/uni-mouse-vision

## Последний коммит
- **Hash:** d1e92fd977ed5586739ceead1c029372ce724d81
- **Дата:** 2026-08-12 14:56:19 +0300
- **Message:** go (включает DIAGNOSTIC-VISIBLE + ночной автоцикл + отчёты)

## Что вошло в пуш (последние коммиты)
- `uni/desktop/` — оверлей Desktop Companion (main.js/app.js/avatar.js/index.html):
  - V-01..V-03 fix (const uni, importmap+three-vrm VRM loaded, позиция у нижней кромки)
  - DIAGNOSTIC-VISIBLE: лог bounds/opacity/scaleFactor + кнопка трея «Диагностика»
  - /api/autonomous/stream 404 fix (оверлей→GET)
- `uni/webui/server.py` — R-01 (/v3), R-02 (_sanitize_secrets), BONUS-01.2 (SSE try/except)
- `tools/` — screenshot.py (Win32), find_overlay_window.py
- `tests/` — test_r_queue, test_api_desktop, test_desktop_p0, test_desktop_proactive, test_api_admin_v3
- `uni-hermes/outbox/` — REPORT_VISUAL_E2E, REPORT_001..007, AUTOMATION_AUDIT/STARTED, MORNING_REPORT
- `UNI_GLOBAL_STATE.md` — статус компонентов

## Важно про ассеты
- `uni/desktop/assets/UNI.vrm` (19.8MB) **УЖЕ отслеживается** в git (добавлен ранее).
  Согласно директиве: не трогать. Репо раздуто на ~20MB — учтите при клонировании.
- `node_modules/` — в .gitignore (не пушится).

## Проверка доступности
- `git remote -v` → origin https://github.com/DieWillz/UNI-test.git ✅
- `git status` → чисто (все изменения закоммичены) ✅
- ahead/behind vs origin → 0/0 (синхронизировано) ✅
- Репо PUBLIC → ссылка открывается для любого ревьюера.

## Для ревьюеров (других ИИ)
Передавайте им ссылку на ветку:
**https://github.com/DieWillz/UNI-test/tree/night/uni-mouse-vision**

Ключевые точки входа для проверки кода:
- Оверлей: `uni/desktop/main.js`, `uni/desktop/renderer/{app,avatar}.js`
- Сервер/админка: `uni/webui/server.py`, `uni/webui/v3/index.html`
- Тесты: `tests/test_*.py`, `uni/desktop/tests/_smoke_desktop_log.cjs`
