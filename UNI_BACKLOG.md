# UNI Backlog

## B-01 Настроить автономный режим управления устройством [ ]
## B-02 Зафиксировать контракт vision capture (screen, не webcam) [V]
## T-01 Собрать замкнутый контур «вижу → кликаю → проверяю» [V]
## T-02 Подключить HumanMouseController к computer.py [V]
## T-03 Цикл act_on_screen под зрением [V]
## T-04 Админка v3: глобальное состояние [V]
## T-05 Админка v3: задачи из backlog [V]
## T-06 Админка v3: heartbeats участников [V]
## T-07 Админка v3: журнал [V]
## T-08 Админка v3: папки участников [V]
## T-15 Кнопка экстренной остановки [V]
## T-16 Валидация входных данных (path traversal) [V]

- [x] FIX-AUDIT: устранить 5 пунктов внешнего аудита
- [x] Vision contract: screen thumbnail из body вместо webcam
- [ ] BONUS-01.1 Локализовать multi_acc_v3_package.py

## INT-04 (Директива 2026-08-13, Дополнение №2): идеи из reuse-candidates
# Источники: UNI-reuse-candidates/HERMES_ANALYSIS.md, NOTES.md.
# Резюме: 3 модуля (tts_sentence_chunker, audio_env_detect, agent_heartbeat)
# — это выжимки из Hermes tools. РЕШЕНИЕ: переиспользовать как каноничные
# модули uni/utils/* (уже сделано: INT-02 tts_sentence_chunker, INT-03
# audio_env_detect). agent_heartbeat → не импортировать hermes_* в uni
# (нарушает инвариант 0.4), а реализовать локально через heartbeat_*.txt
# (ADM-01 /api/admin/agents). README.md reuse-candidates — внутренний
# справочник Hermes, НЕ копировать в канон.

## I-01 Интегрировать tts_sentence_chunker в speech.py [V] (INT-02)
## I-02 Интегрировать audio_env_detect в /api/uni/status [V] (INT-03)
## I-03 Heartbeat-модуль агентов: НЕ импортировать hermes agent_heartbeat;
#        использовать uni-*/logs/heartbeat*.txt + bridge/heartbeat_*.txt [V] (ADM-01)
## I-04 Справочник reuse-candidates/README.md: оставить как источник,
#        не копировать в канон [V]
# ПРОТИВОРЕЧИЙ МАНИФЕСТУ: нет (все идеи совпадают: reuse, fail-closed,
# честные статусы, heartbeat-наблюдаемость).
