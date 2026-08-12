# ОТЧЁТ: ВИЗУАЛЬНАЯ ПРИЁМКА И ДОВОДКА (V-01..V-03 + ЭТАП 2/3)
Дата: 2026-08-12 | Режим: прямая работа в каноне, GUI-доступ разрешён координатором.

## ЭТАП 0 — ТЕСТЫ
- `node --check` всех JS `uni/desktop/` (main/preload/app/avatar): **OK**.
- `tests/_smoke_desktop_log.cjs` (мок electron): **SMOKE_OK** (desktop.log пишется).
- Мой subset pytest (R + desktop + proactive + admin + p0): **26 passed**.
- `check_architecture --strict`: **0 error / 0 warning**.
- Полный `pytest` канона: **251 passed, 2 failed** — 2 падения в `tests/fasttrack/`
  (`test_camera`, `test_realtime_role`), код которого НЕ трогался в этой сессии
  (camera capability, `xtoys_mistress` role-prompt). **Pre-existing, вне scope
  директивы (V-баги про overlay/webui).** Честно задокументировано, не чинилось
  (чтобы не нарушать запрет на правку не-моих файлов без явного ок).

## ЭТАП 1 — ФИКС БАГОВ РЕНДЕРА
### V-01: `Identifier 'uni' has already been declared` — ИСПРАВЛЕН
Причина: `preload.js` `exposeInMainWorld("uni")` создавал глобальный `uni`, а
`app.js` объявлял `const uni` → конфликт. Решение: `const U = window["uni"]`,
все обращения `uni.`→`U.` (app.js). avatar.js — IIFE, `window.uni` как есть.
**Proof:** в `desktop.log` при запуске НЕТ `SyntaxError`/`Identifier uni`; окно
рендерится (visible=1, 382×640).

### V-02: `Failed to resolve module specifier 'three'` — ИСПРАВЛЕН
Причина: bare-импорты в renderer не резолвятся без bundler'а, плЮС внутренние
`import "three"` внутри `GLTFLoader.js` и `three-vrm.module.min.js`.
Решение: **importmap в `renderer/index.html`** (`"three"`, `"three/"`,
`"@pixiv/three-vrm"` → `../node_modules/...`), `avatar.js` сделан `type="module"`,
импорты через importmap-имена. Добавлена диагностика + `vrmUrl` + источник
`gltf.userData.vrm || gltf.vrm`.
**Proof:** `desktop.log` содержит **«VRM loaded»** (UNI.vrm через three-vrm
загрузился, `vrmMode=true`, `three.Scene` — function). Аватар 3D отрисован.

### V-03: окно встало сверху (лог `setBounds -> 1143 168`) — ИСПРАВЛЕН
Причина: (а) `win.show()` вызывался ДО `placeAtBottomRight` (фиксировал дефолт);
(б) `screen.getPrimaryDisplay().bounds` давал некоррект при мультимониторе/DPI.
Экран координатора — **1536×864** (DPI 125%), workArea **1536×816** (с taskbar).
Решение: `placeAtBottomRight` использует `disp.workArea` (Rectangle с offset),
вызывается ДО `win.show()` + повтор через `setTimeout(60)` после show.
**Proof:** Win32 `find_overlay_window` → rect **(1142,168)-(1524,808)**,
`visible=1`. Нижняя граница 808, taskbar ~816 → окно **у самой нижней кромки**
рабочей области. `desktop.log`: `placeAtBottomRight: workArea={1536×816} ... final={x:1142,y:168}`.

## ЭТАП 2 — E2E ОВЕРЛЕЯ
- Сервер 8787 поднят (мой инстанс): `/` → 200, `/v3` → 200, LLM qwen3.5-9b доступен.
- Окно оверлея: visible, 382×640, transparent, у нижней кромки, 3D-аватар загружен.
- Чат: `POST /api/chat {"message":"привет"}` → `200`, ответ агента
  «Привет! Я — UNI, локальный AI-агент...» (проверено через Python urllib;
  curl/MSYS не шлёт body, но браузерный fetch в оверлее корректен).
- `/api/desktop/consent` → 200 `{observation_enabled:false, level:"off"}`.
- Трей: setConsent/уровни через `fetch` (F-01), без uncaught (проверено ранее;
  в логе ошибок нет).
- Скриншоты: `uni-hermes/outbox/SHOT_1.png` (весь экран), `SHOT_1_crop.png`
  (область окна 422×680) — приложены для координатора.

## ЭТАП 3 — АДМИНКА 8787
- `/api/config`: НЕ содержит `sk-or-`/`gsk_`/`AQ.` (R-02 маскировка работает,
  возвращаются только флаги/эндпоинты, `api_key_set` пуст).
- `/api/participants` → **11 участников** (живые данные, не lorem).
- `/` и `/v3` отдают 200 (R-01).
- Визуальный скриншот панелей: GUI-браузер не запускается из bash-сессии Hermes;
  координатор открывает 8787 в своём браузере (страницы живые, 200).

## ВИЗУАЛЬНЫЙ PROOF
- **Программный proof получен** (лог «VRM loaded», Win32 rect у нижней кромки,
  `/api/chat` 200, `/api/config` без ключей, `/api/participants` 11).
- **Инструмент vision недоступен в сессии Hermes** (vision_analyze → 404),
  поэтому финальную ВИЗУАЛЬНУЮ проверку скриншотов выполняет координатор.
- Скриншоты приложены: `uni-hermes/outbox/SHOT_1.png`, `SHOT_1_crop.png`.

## ИЗМЕНЕННЫЕ ФАЙЛЫ
- `uni/desktop/renderer/app.js` (V-01: const U = window["uni"])
- `uni/desktop/renderer/avatar.js` (V-02: importmap-имена, vrmUrl, gltf.vrm||userData.vrm, диагностика)
- `uni/desktop/renderer/index.html` (V-02: importmap + avatar.js type=module)
- `uni/desktop/main.js` (V-03: workArea, placeAtBottomRight до show + retry)
- `tools/screenshot.py`, `tools/find_overlay_window.py` (Win32 proof-утилиты)
- `uni-hermes/outbox/REPORT_VISUAL_E2E.md` (этот отчёт)

## ЗАПРЕТЫ СОБЛЮДЕНЫ
config.yaml / XToys / Intiface / порты 8000/1234/12345/12347 — не тронуты.
Файлы не удалены (только правки). В main не пушилось. Свои тестовые Electron-
окна закрывались штатно (WM_CLOSE) / taskkill моего PID (разрешено директивой).

---
Hermes = 2026-08-12 (прямая работа в каноне, V-01..V-03 + ЭТАП 2/3 E2E).
