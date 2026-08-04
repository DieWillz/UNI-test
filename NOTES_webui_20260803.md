# WebUI / Council — правки после раунда 20260803-004945

Дата: 2026-08-03 · Автор правок: Hermes

## Что изменено

| Файл | Суть |
|------|------|
| `uni/webui/index.html` | режимы переклички API/Браузер/Все; модалка «некого опрашивать»; popover политики; кнопки копирования журнала + копирование отдельной строки; кликабельная ссылка на файл отчёта; авто-опрос статусов раз в 4 с |
| `uni/webui/server.py` | честные статусы API (`_tcp_open` / `_dns_ok`); `/api/report` отдаёт `path` + `raw_url`; новый `/api/report/raw`; заглушка `/favicon.ico` |
| `uni/council/_keys.py` | endpoint может задавать `model` в config |
| `uni/council/participants.py` | `model` из config переопределяет реестр |
| `config.yaml` | починен битый `base_url` Gemini; ключ Gemini обнулён (был склеен); Hermes → `http://127.0.0.1:1234/v1` + `model: qwen3.5-9b`; OpenRouter → `model: deepseek/deepseek-chat-v3.1:free` |

## Проверено вживую

- CDP 9222 жив; DeepSeek/QWEN/Qwen Coder/Claude/Grok = `ready`
- Hermes теперь `ready` (LM Studio на 1234), а не ложный `configured`
- Gemini честно `unavailable` (нет ключа), ChatGPT `unavailable` (нет codex в PATH)
- Режим «Браузер» даёт 5 целей вместо пустого списка (это и была «тишина»)
- `pytest`: 111 passed · `check_architecture.py`: 0 errors · 0 JS-ошибок в консоли

## Что нужно сделать человеку

1. **OpenRouter** — старый ключ даёт `403 Key limit exceeded`. Выпусти новый на openrouter.ai и вставь в Настройки → API (модель уже переключена на `:free`).
2. **Gemini** — прежний ключ в config был склеен из трёх копий и битый; вставь корректный. Если снова `getaddrinfo failed` — это DNS/сеть до Google, не ключ.
3. **Hermes (локальный)** — держи LM Studio запущенным на `127.0.0.1:1234`, иначе статус станет `unavailable` (это правильное поведение).
4. **ChatGPT/Codex** — вне scope: нужен `codex` в PATH.

## Проверка за 2 минуты

```
cd C:\LLM\UNI && set PYTHONPATH=C:\LLM\UNI && C:\LLM\python312\python.exe -m uni.webui --port 8787
```
Открыть http://127.0.0.1:8787/ → «Проверить участников» → выбрать режим переклички → «Перекличка».
Отчёт: вкладка отчёта, строка `📄 C:\LLM\UNI\.uni-council\<id>_report.md` кликабельна.
