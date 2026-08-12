# ОТЧЁТ: FIX-VISUAL-01 — исправление визуальных багов оверлея
Дата: 2026-08-12
Задача: BUG#1 (const uni дубль), BUG#2 (three import), BUG#3 (позиция окна).
Режим: прямая работа в каноне.

## BUG #1 (критический): Identifier 'uni' has already been declared
**Причина:** `preload.js` делает `contextBridge.exposeInMainWorld("uni", {...})` —
это создаёт ГЛОБАЛЬНУЮ переменную `uni` в renderer. А `app.js` объявлял
`const uni = window.uni || null;` в global scope → конфликт `Identifier 'uni' has already been declared`.
JS падал целиком → окно пустое.

**Решение (по директиве п.3: ноль const uni в global scope):**
- Удалён `const uni` из `renderer/app.js`.
- Вместо него локальная `const U = window["uni"] || null;` (имя `U`, не конфликтует с глобальным `uni`).
- Все обращения `uni.x` → `U.x` в app.js. В `avatar.js` `window.uni` используется как есть (IIFE, локально, конфликта нет).
- Проверка: `grep -rn "const uni|let uni|var uni" renderer/` → только в комментарии, НЕТ объявлений.

**Proof:** node --check всех JS OK; smoke-тест (мок electron) → SMOKE_OK без SyntaxError.

## BUG #2 (средний): Failed to resolve module specifier 'three'
**Причина:** Electron renderer не резолвит bare-импорты (`import "three"`) без bundler'а.

**Решение:** в `renderer/avatar.js` `loadVRM()` импорты заменены на локальные пути
(не зависят от сети/CDN):
```
const modThree = await import("../node_modules/three/build/three.module.js");
const modVrm = await import("../node_modules/@pixiv/three-vrm/lib/three-vrm.module.min.js");
const { GLTFLoader } = await import("../node_modules/three/examples/jsm/loaders/GLTFLoader.js");
```
Файлы физически присутствуют (проверено: three.module.js 1.27MB, three-vrm.module.min.js 149KB, GLTFLoader.js 109KB).
Обёртка try/catch → при ошибке import SVG-fallback (без краша в консоль).

## BUG #3 (косметический): позиция окна не у нижней кромки
**Лог координатора:** `setBounds {"x":577,"y":88}` — верхняя часть экрана.

**Причина:** использовался `screen.getPrimaryDisplay().workAreaSize` — он уменьшен на
taskbar/DPI и может давать окно не внизу. Плюс лог печатал исходные bounds ДО setPosition.

**Решение (в `placeAtBottomRight`):**
- Используется `screen.getPrimaryDisplay().bounds` (физический экран целиком) → окно
  ставится у нижней правой кромки физического экрана.
- Лог теперь пишет: `screenBounds`, `winSize`, `set->x,y`, и **ФИНАЛЬНЫЕ координаты**
  (`final=` через `win.getBounds()` ПОСЛЕ `setPosition`).
- Координатор перепроверит визуально по `desktop.log`.

## Файлы изменены
- `uni/desktop/renderer/app.js` (BUG#1: const U = window["uni"], все uni→U)
- `uni/desktop/renderer/avatar.js` (BUG#2: локальные пути three-vrm)
- `uni/desktop/main.js` (BUG#3: bounds экрана + финальные координаты в лог)

## Тесты (proof of work)
- `node --check` всех JS: OK (main/preload/app/avatar).
- `tests/_smoke_desktop_log.cjs` → SMOKE_OK (без SyntaxError).
- pytest сьют: **26 passed**, 0 failed.
- `check_architecture --strict`: 0 error, 0 warning.

## Визуальный proof (для координатора, на GUI-машине)
`cd uni/desktop && start.bat` (или `npx electron .`):
- окно с аватаром (UNI.vrm 3D или SVG-fallback) у НИЖНЕЙ кромки;
- чат работает, кнопки реагируют, трей «Показать» работает;
- `desktop.log` содержит `placeAtBottomRight: ... final= {...}` с y близким к низу экрана.

## Соблюдение запретов
WebUI 8787 не тронут, config.yaml/XToys/Intiface/порты/процессы не тронуты. Файлы не удалены.

---
Hermes = 2026-08-12 (прямая работа в каноне, FIX-VISUAL-01).
