# Задача: Проверка R-01/R-02 визуально-программно

## СЕКЦИЯ HERMES
- R-01: GET /v3 -> 200, отдаёт uni/webui/v3/index.html.
- R-02: GET /api/config не содержит sk-or-/gsk_/AQ./hf_/Bearer (маскировка).
Proof: HTTP-статусы + grep по ответу в `uni-hermes/outbox/REPORT_R_visual.md`.
