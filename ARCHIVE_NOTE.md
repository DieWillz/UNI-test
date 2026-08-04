# ARCHIVE_NOTE — параллельные копии репозитория (НЕ канон)

Канон = `C:\LLM\UNI` (пакет `uni/`). Ниже перечислены параллельные/архивные
копии дерева внутри `C:\LLM\UNI`. Они — **справочные материалы**, их нельзя
запускать, редактировать или импортировать из них код в канон.

Перечислено сканированием `C:\LLM\UNI` (2026-08-04, ночная смена Hermes):

- `backup/` — старая резервная копия (в .gitignore).
- `Claude/`, `Uni-Claude/`, `Uni-DeepSeek/`, `Uni-OpenCode/` — копии других ИИ.
- `uni/backup/`, `uni/Claude/`, `uni/uni/` — вложенные дубли (в .gitignore).
- `uni Hermes old/` — параллельная сборка другого ИИ (возможно СТАРШЕ по mtime).
- `copilot-worktrees/UNI/diewillz-upload-files/` — worktree Copilot, удалённые файлы
  видны в `git status` как `D`; не трогать, не коммитить.
- `agent-browser/` — рантайм-профиль/логи браузера (в .gitignore).
- `uni/webui/for-chat/` — ПОЛОЖЕНО ПОЛЬЗОВАТЕЛЕМ: 9 git-репозиториев клиентов
  Buttplug/Intiface (buttplug-py, buttplug-js, ButtplugLLM, remotetoys, плагины
  SillyTavern). Не канон; нужно для изучения, не для запуска как есть.
- `config-old.yml` — старая копия конфига (в .gitignore).

Физически НЕ удалено (решение за пользователем утром).
