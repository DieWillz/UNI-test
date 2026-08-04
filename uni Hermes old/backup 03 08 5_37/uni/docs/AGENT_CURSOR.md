# Курсор агента UNI — browser overlay + desktop badge

Windows не даёт две аппаратные мыши. Два разных механизма:

## 1. Browser (Playwright / CDP) — must-have

Файлы: `uni/agent_cursor.py`, хуки в `browser_session.py`, `capabilities/browser.py`, `council/provider.py`.

- В страницу инжектится DOM-метка «UNI».
- Перед click/fill метка едет к элементу; клик — DOM, системная мышь не двигается.
- `install_on_context` — на все новые документы контекста.

```yaml
capabilities:
  browser:
    headless: false
    agent_cursor:
      enabled: true
      label: "UNI"
      move_ms: 220
```

## 2. Desktop (pyautogui) — action badge

Файлы: `uni/capabilities/uni_action_badge.py`, `capabilities/computer.py`.

- Always-on-top бейдж (tkinter, stdlib).
- ~0.45 с рядом с точкой клика: UNI · click.
- Системный курсор всё равно едет (лимит ОС); бейдж помечает действие агента.
- Нет tkinter / нет GUI → silent no-op.

```yaml
capabilities:
  computer:
    action_badge: true
    action_badge_label: "UNI"
```

## Проверка

Browser: CDP + вкладка → Запустить раунд → метка UNI на странице, твоя мышь на месте.

Desktop: клик по координатам → курсор ОС + бейдж UNI.
