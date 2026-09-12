from __future__ import annotations

from uni.operator.routing import looks_like_operator_task


def test_multistep_desktop_or_browser_command_routes_to_operator() -> None:
    assert looks_like_operator_task("Открой браузер, найди Blender и скачай установщик")
    assert looks_like_operator_task("Найди последний PDF и сохрани копию на рабочий стол")
    assert looks_like_operator_task("Открой блокнот, напиши текст, затем сохрани файл")


def test_conversation_and_simple_legacy_commands_do_not_force_operator() -> None:
    assert not looks_like_operator_task("Что такое Playwright?")
    assert not looks_like_operator_task("найди в интернете Blender")


def test_device_commands_never_route_through_general_computer_operator() -> None:
    assert not looks_like_operator_task("открой XToys и поставь мощность 20")
    assert not looks_like_operator_task("интенсивность 30")


def test_simple_launch_commands_route_to_operator() -> None:
    """Simple launch commands like 'открой Пуск', 'открой Paint' go to Operator."""
    assert looks_like_operator_task("открой Пуск")
    assert looks_like_operator_task("открой Paint")
    assert looks_like_operator_task("открой сайт coral travel")
    assert looks_like_operator_task("запусти калькулятор")
    assert looks_like_operator_task("open start")
    assert looks_like_operator_task("launch notepad")


def test_visual_only_targets_stay_in_fallback() -> None:
    """'открой блокнот' now goes to Operator (launch marker rule)."""
    assert looks_like_operator_task("открой блокнот")
    assert looks_like_operator_task("открой notepad")


def test_greeting_and_questions_do_not_route_to_operator() -> None:
    assert not looks_like_operator_task("привет")
    assert not looks_like_operator_task("Юни, как дела?")
    assert not looks_like_operator_task("что ты умеешь")

def test_single_action_in_existing_computer_context_routes_to_operator() -> None:
    assert looks_like_operator_task("\u0412 \u043c\u043e\u0451\u043c \u043e\u0442\u043a\u0440\u044b\u0442\u043e\u043c \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u043d\u0430\u0439\u0434\u0438 \u043d\u0443\u0436\u043d\u0443\u044e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0443")
    assert looks_like_operator_task("\u0412 \u044d\u0442\u043e\u043c \u043e\u043a\u043d\u0435 \u043d\u0430\u0436\u043c\u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c")
    assert not looks_like_operator_task("\u043d\u0430\u0439\u0434\u0438 \u0432 \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\u0435 Blender")
