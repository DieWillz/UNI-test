# Задача: Проверка SSE desktop/events (D-13 proactive)

## СЕКЦИЯ HERMES
Сервер жив. GET /api/desktop/events должен держать SSE-поток (text/event-stream).
Проверь: curl -N --max-time 4 http://127.0.0.1:8787/api/desktop/events -> заголовок
text/event-stream и хотя бы один `: ping` или `data:`.
Proof: вывод curl в `uni-hermes/outbox/REPORT_sse.md`.
