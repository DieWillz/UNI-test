"""Извлечённые модули EventLoop (P-06, 2026-08-17).

EventLoop в uni/event_loop.py — ~950 строк, нарушает SRP. Мы извлекаем
чистые функции и классы в подмодули, которые EventLoop может
**делегировать** через аддитивный флаг (default off, для обратной
совместимости):

  UNI_EVENTLOOP_MODULAR=1  — включает делегирование в новые модули
  (по умолчанию старый монолитный код работает как раньше)

Модули:
  - command_parser  — parse_direct_command(), is_stop_command() (чистые функции)
  - visual_router   — _try_visual_command() как чистая функция
  - camera_watch    — _camera_watch_worker + _start_camera_watch
  - screen_watch    — _watch_screen_loop + _start_screen_watch
  - exploration     — _explore_web + _next_exploration_query
  - autonomous_bridge — _maybe_autonomous_override

Каждый модуль имеет свои тесты (tests/test_loops_*.py), что решает
проблему «EventLoop слишком большой чтобы тестировать изолированно».
"""
