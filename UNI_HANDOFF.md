# UNI_HANDOFF

task_id: UNI:HRM:2026-08-11-N04B
from_agent: HERMES
to_agent: UNI (или следующий Hermes после Wake)

context:
Ночной контур мышь+зрение завершён (N-00..N-09). Цель N-04b: голосовая/текстовая
маршрутизация «открой X» / «кликни X» -> VisualActionAgent.act_on_screen(goal).

completed_work:
- N-00..N-09 done, 2 коммита в night/uni-mouse-vision (00c9a03, 1984b78, fa37a1a).
- Создана инфраструктура цикла: UNI_SHIFT_STATE, UNI_DO_NOT_TOUCH, UNI_JOURNAL, UNI_CYCLE_STATE, heartbeat.

open_questions:
- где лучше вешать маршрутизацию: в Agent (новый метод) или event_loop.run_cycle (ядро, риск).

permissions:
- править uni/agent.py (добавить метод act_on_screen + включить use_human_motion).
- запускать pytest/check_architecture.
- зеркалировать в uni-local/uni.

next_expected_result:
- Agent.act_on_screen(goal) работает; тест на mock пройден; check_architecture 0/0.
