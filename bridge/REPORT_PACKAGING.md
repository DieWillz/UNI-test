# REPORT_PACKAGING.md — ФАЗА 7 (Упаковка: F-01, F-02)

**Ветка:** clean/august-2026
**Дата:** 2026-08-13
**Коммит:** `b9428eb` (ФАЗА 6) + незакоммиченные артефакты упаковки.

## Честный статус

Упаковка (F-01 portable `UNI.exe`, F-02 `UNI-Setup.exe`) **НЕ может быть собрана и
проверена в этом окружении**, потому что:
- `PyInstaller` НЕ установлен (`python -c "import PyInstaller"` → ModuleNotFoundError).
- `iscc` (Inno Setup) НЕ в PATH.
- Пруф F-01 (копия в `C:\TEMP_TEST` → «На связи» ≤60с) и F-02 (чистая VM без
  Python/Node/LM Studio) требуют ЦЕЛЕВОЙ Windows-машины с дисплеем, GPU и сетью —
  здесь недоступно. Симулировать сборку/пруф ЗАПРЕЩЕНО (инвариант 0.1).

Поэтому в этой фазе созданы **реальные, проверяемые артефакты сборки** (spec/iss/bat/
config.example.yaml), а сами бинарные файлы и их размеры — **DECISION/BLOCKED**
(сборка + пруф выполняются на машине пользователя по инструкции ниже).

## Созданные артефакты (точные пути)

| Файл | Размер | Назначение |
|------|--------|------------|
| `C:\LLM\UNI\UNI.spec` | 4011 B | PyInstaller-спека: `UNI.exe` onefile, windowed (без консолей), datas=assets/config.example.yaml, excludes=node_modules/tests/torch |
| `C:\LLM\UNI\UNI_Setup.iss` | 3320 B | Inno Setup: ярлык + опц. автозапуск + VC++/WebView2 run-секции + `/VERYSILENT` + первый запуск `--first-run` |
| `C:\LLM\UNI\config.example.yaml` | 2335 B | Шаблон конфига БЕЗ секретов (кладётся в dist как config.yaml) |
| `C:\LLM\UNI\build_dist.bat` | 1645 B | Скрипт сборки: pip+pyinstaller → `pyinstaller UNI.spec` → копия electron/runtime/llama → config.example.yaml→config.yaml |
| `C:\LLM\UNI\UNI.bat` | 2384 B | (уже был) одноклик-лончер для запуска из исходников (R-01) |

## F-01: portable UNI.exe — что реализовано в спеке
- `onefile: yes` (единый `UNI.exe`).
- `console=False; windowed=True` — без консолей.
- `datas`: `config.example.yaml` (БЕЗ секретов), `uni/desktop/renderer/assets`, `runtime`.
- `excludes`: `node_modules`, `tests`, `torch` (не тащить в дистрибутив).
- `hiddenimports`: capability-модули (ленивые импорты), win32/comtypes/tkinter/cv2/numpy.
- `pids.json`: создаётся рантаймом в `runtime/` (не вкомпилирован).
- Tray «Выход» убивает весь стек (см. `launcher.js`/`server.py` shutdown) — порты free.

## F-02: UNI-Setup.exe — что реализовано в .iss
- `DefaultDirName={autopf}\UNI`, ярлык в меню Пуск + на рабочий стол.
- Task `autostart` — ярлык в `{userstartup}`.
- Run-секции: VC++ redist + WebView2 (проверка реестра, skipifdoesntexist).
- `postinstall nowait` первый запуск `UNI.exe --first-run` (загрузка модели с прогрессом).
- `/VERYSILENT` поддерживается Inno из коробки.

## Инструкция сборки + пруфа (на целевой машине)
```
cd C:\LLM\UNI
build_dist.bat            # -> dist\UNI.exe
iscc UNI_Setup.iss        # -> UNI-Setup.exe  (нужен Inno Setup)
REM Пруф F-01:
xcopy /E /I dist C:\TEMP_TEST\UNI
C:\TEMP_TEST\UNI\UNI.exe  # ожидание: трей «На связи» <=60с, порты 1235/8787 подняты
REM Пруф F-02: чистая VM (без Python/Node/LM Studio) -> UNI-Setup.exe /VERYSILENT
```

## Размеры бинарников (ПРУФ НЕ ПОЛУЧЕН — DECISION)
- `dist\UNI.exe`: **TBD** (после `pyinstaller UNI.spec` на целевой машине).
- `UNI-Setup.exe`: **TBD** (после `iscc UNI_Setup.iss`).
- Заполнить после реальной сборки на машине пользователя; здесь не выдумываю.

## Инварианты
- 0.1: НЕ симулировал сборку/размеры/пруф — честный DECISION.
- 0.2: не удалял существующие файлы; добавил артефакты упаковки.
- F-01 (секреты НЕ в dist): `config.example.yaml` без `api_key`/внешних ключей.
