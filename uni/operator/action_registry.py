from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import PermissionLevel


@dataclass(frozen=True)
class ActionSpec:
    name: str
    capability: str
    action: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    permission: PermissionLevel = PermissionLevel.LOCAL_REVERSIBLE
    side_effect: bool = False
    physical_input: bool = False
    requires_target: bool = False
    verification: str = "explicit_postcondition"
    expose_to_llm: bool = False

    @property
    def api_name(self) -> str:
        return self.name.replace(".", "_")

    def tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.api_name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: ActionSpec) -> ActionSpec:
        if spec.name in self._specs:
            raise ValueError(f"duplicate action: {spec.name}")
        if "." not in spec.name or not spec.capability or not spec.action:
            raise ValueError(f"invalid action spec: {spec.name}")
        self._specs[spec.name] = spec
        self._aliases[spec.api_name] = spec.name
        return spec

    def canonical_name(self, name: str) -> str:
        return self._aliases.get(name, name)

    def register_alias(self, alias: str, name: str) -> None:
        """Compatibility names share the canonical spec, never another route."""
        canonical = self.get(name).name
        if alias in self._specs or alias in self._aliases:
            raise ValueError(f"duplicate action alias: {alias}")
        self._aliases[alias] = canonical

    def get(self, name: str) -> ActionSpec:
        canonical = self.canonical_name(name)
        try:
            return self._specs[canonical]
        except KeyError as exc:
            raise KeyError(f"unregistered action: {name}") from exc

    def has(self, name: str) -> bool:
        try:
            self.get(name)
            return True
        except KeyError:
            return False

    def route(self, name: str) -> tuple[str, str]:
        spec = self.get(name)
        return spec.capability, spec.action

    def tool_schemas(self, enabled_capabilities: set[str] | None = None) -> list[dict[str, Any]]:
        return [
            spec.tool_schema()
            for spec in self._specs.values()
            if spec.expose_to_llm
            and (enabled_capabilities is None or spec.capability in enabled_capabilities)
        ]

    def planner_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "params": spec.parameters,
                "required": list(spec.required),
                "permission": spec.permission.value,
                "side_effect": spec.side_effect,
                "physical_input": spec.physical_input,
                "requires_target": spec.requires_target,
                "verification": spec.verification,
            }
            for spec in self._specs.values()
        ]

    def names(self) -> list[str]:
        return list(self._specs)


def _s(type_: str, **kwargs: Any) -> dict[str, Any]:
    return {"type": type_, **kwargs}


def _add(registry: ActionRegistry, name: str, capability: str, action: str,
         description: str, *, parameters: dict[str, Any] | None = None,
         required: tuple[str, ...] = (), permission: PermissionLevel = PermissionLevel.LOCAL_REVERSIBLE,
         side_effect: bool = False, physical_input: bool = False, requires_target: bool = False,
         verification: str = "explicit_postcondition", expose: bool = False) -> None:
    registry.register(ActionSpec(
        name=name, capability=capability, action=action, description=description,
        parameters=parameters or {}, required=required, permission=permission,
        side_effect=side_effect, physical_input=physical_input, requires_target=requires_target,
        verification=verification, expose_to_llm=expose,
    ))


def build_default_registry() -> ActionRegistry:
    r = ActionRegistry()
    _add(r, "browser.navigate", "browser", "navigate", "Открыть URL в управляемом браузере",
         parameters={"url": _s("string")}, required=("url",), side_effect=True,
         verification="browser_location", expose=True)
    _add(r, "browser.search_web", "browser", "search_web", "Найти информацию в интернете",
         parameters={"query": _s("string")}, required=("query",), verification="browser_location", expose=True)
    _add(r, "browser.search_images", "browser", "search_images", "Найти изображения в интернете",
         parameters={"query": _s("string")}, required=("query",), verification="browser_location", expose=True)
    _add(r, "browser.extract_text", "browser", "extract_text", "Прочитать текст активной страницы",
         parameters={"max_chars": _s("integer", minimum=100, maximum=20000)},
         permission=PermissionLevel.READ, verification="fresh_browser_read", expose=True)
    _add(r, "browser.current_tab", "browser", "current_tab", "Прочитать URL и заголовок активной вкладки",
         permission=PermissionLevel.READ, verification="fresh_browser_read", expose=True)
    _add(r, "browser.screenshot", "browser", "screenshot", "Снять активную вкладку",
         permission=PermissionLevel.READ, verification="fresh_browser_read")
    _add(r, "browser.save_screenshot", "browser", "save_screenshot", "Сохранить скриншот активной вкладки",
         parameters={"label": _s("string")}, side_effect=True, verification="file_observation")
    _add(r, "browser.click_selector", "browser", "click_selector", "Legacy DOM click by fixed caller selector",
         parameters={"selector": _s("string")}, required=("selector",), side_effect=True)
    _add(r, "browser.type_selector", "browser", "type_selector", "Legacy DOM fill by fixed caller selector",
         parameters={"selector": _s("string"), "text": _s("string")}, required=("selector", "text"), side_effect=True)
    _add(r, "computer.launch", "computer", "launch", "Запустить приложение",
         parameters={"app": _s("string")}, required=("app",), side_effect=True,
         physical_input=False, verification="window_exists")
    _add(r, "computer.click", "computer", "click", "Физический клик мышью",
         parameters={"x": _s("integer"), "y": _s("integer"), "button": _s("string")},
         required=("x", "y"), side_effect=True, physical_input=True)
    _add(r, "computer.move", "computer", "move", "Переместить мышь",
         parameters={"x": _s("integer"), "y": _s("integer")}, required=("x", "y"),
         side_effect=True, physical_input=True)
    for dotted, action, description in (
        ("computer.click_human", "click_human", "Человеко-подобный клик"),
        ("computer.double_click_human", "double_click_human", "Двойной человеко-подобный клик"),
    ):
        _add(r, dotted, "computer", action, description,
             parameters={"x": _s("integer"), "y": _s("integer"), "button": _s("string")},
             required=("x", "y"), side_effect=True, physical_input=True)
    _add(r, "computer.drag_human", "computer", "drag_human", "Перетащить мышью",
         parameters={"x1": _s("integer"), "y1": _s("integer"), "x2": _s("integer"), "y2": _s("integer"), "button": _s("string")},
         required=("x1", "y1", "x2", "y2"), side_effect=True, physical_input=True)
    for dotted, action, description in (
        ("computer.type", "type", "Ввести текст клавиатурой"),
        ("computer.type_unicode", "type_unicode", "Ввести Unicode-текст"),
        ("computer.paste", "paste", "Вставить текст через буфер"),
    ):
        _add(r, dotted, "computer", action, description,
             parameters={"text": _s("string")}, required=("text",), side_effect=True, physical_input=True)
    _add(r, "computer.press", "computer", "press", "Нажать клавишу или hotkey",
         parameters={"key": _s("string")}, required=("key",), side_effect=True, physical_input=True)
    _add(r, "computer.press_window_hotkey", "computer", "press_window_hotkey", "Нажать hotkey окна",
         parameters={"key": _s("string")}, required=("key",), side_effect=True, physical_input=True)
    _add(r, "computer.delete_backward", "computer", "delete_backward", "Удалить символы назад",
         parameters={"count": _s("integer", minimum=1, maximum=10000)}, side_effect=True, physical_input=True)
    _add(r, "computer.copy_selected_text", "computer", "copy_selected_text", "Скопировать выделенный текст",
         permission=PermissionLevel.READ, side_effect=True, physical_input=True, verification="clipboard_read")
    for dotted, action, param in (
        ("computer.focus_window", "focus_window", "title"),
        ("computer.focus_app", "focus_app", "app"),
    ):
        _add(r, dotted, "computer", action, "Сфокусировать окно/приложение",
             parameters={param: _s("string")}, required=(param,), side_effect=True,
             physical_input=True, verification="active_window")
    _add(r, "computer.find_accessible_element", "computer", "find_accessible_element", "Найти UIA-элемент",
         parameters={"name": _s("string"), "control_type": _s("string")}, required=("name",),
         permission=PermissionLevel.READ, verification="fresh_uia_read")
    _add(r, "computer.focus_accessible_element", "computer", "focus_accessible_element", "Сфокусировать UIA-элемент",
         parameters={"name": _s("string"), "control_type": _s("string")}, required=("name",),
         side_effect=True, physical_input=True)
    _add(r, "computer.inspect_accessible_elements", "computer", "inspect_accessible_elements", "Получить bounded UIA snapshot активного окна",
         parameters={"max_elements": _s("integer", minimum=1, maximum=200)},
         permission=PermissionLevel.READ, verification="fresh_uia_read")
    for dotted, action, description in (
        ("computer.read_accessible_value", "read_accessible_value", "Прочитать значение UIA-поля"),
        ("computer.read_accessible_text", "read_accessible_text", "Прочитать UIA-текст активного окна"),
        ("computer.read_focused_accessible_text", "read_focused_accessible_text", "Прочитать сфокусированный UIA-элемент"),
        ("computer.list_accessible_fields", "list_accessible_fields", "Получить видимые UIA-поля"),
        ("computer.list_visible_windows", "list_visible_windows", "Получить список видимых окон"),
    ):
        parameters = {}
        if action == "read_accessible_value": parameters = {"name": _s("string")}
        if action == "read_accessible_text": parameters = {"max_chars": _s("integer", minimum=100, maximum=20000)}
        if action == "list_accessible_fields": parameters = {"max_fields": _s("integer", minimum=1, maximum=100)}
        required = ("name",) if action == "read_accessible_value" else ()
        _add(r, dotted, "computer", action, description, parameters=parameters, required=required,
             permission=PermissionLevel.READ, verification="fresh_uia_read")
    for dotted, action in (
        ("computer.set_accessible_value", "set_accessible_value"),
        ("computer.replace_accessible_text", "replace_accessible_text"),
    ):
        _add(r, dotted, "computer", action, "Установить значение UIA-поля",
             parameters={"name": _s("string"), "text": _s("string")}, required=("name", "text"),
             side_effect=True, verification="uia_value")
    for dotted, action, description in (
        ("camera.start", "start", "Запустить камеру"),
        ("camera.snapshot", "snapshot", "Сделать снимок камеры"),
        ("camera.stop", "stop", "Остановить камеру"),
    ):
        _add(r, dotted, "camera", action, description,
             permission=PermissionLevel.READ if action == "snapshot" else PermissionLevel.LOCAL_REVERSIBLE,
             side_effect=action != "snapshot", verification="camera_state")
    _add(r, "speech.speak", "speech", "speak", "Произнести текст",
         parameters={"text": _s("string")}, required=("text",), side_effect=True, verification="transport_only")
    _add(r, "speech.listen", "speech", "listen", "Распознать речь",
         permission=PermissionLevel.READ, verification="fresh_audio_read")
    _add(r, "speech.synthesize_file", "speech", "synthesize_file", "Создать аудиофайл",
         parameters={"text": _s("string"), "path": _s("string")}, required=("text",),
         side_effect=True, verification="file_observation")
    for dotted, action, description in (
        ("vision.analyze_screen", "analyze_screen", "Описать активную вкладку"),
        ("vision.find_element", "find_element", "Найти элемент на вкладке"),
        ("vision.analyze_desktop", "analyze_desktop", "Описать рабочий стол"),
        ("vision.observe_desktop", "observe_desktop", "Наблюдать рабочий стол"),
        ("vision.find_desktop_element", "find_desktop_element", "Найти элемент рабочего стола"),
        ("vision.analyze_file", "analyze_file", "Проанализировать изображение/файл"),
    ):
        params = {"prompt": _s("string")} if "analyze" in action else {"description": _s("string")}
        _add(r, dotted, "vision", action, description, parameters=params,
             permission=PermissionLevel.READ, verification="fresh_visual_read",
             expose=dotted in {"vision.analyze_screen", "vision.analyze_desktop"})
    xtoys_specs = (
        ("xtoys.open", "open", "Открыть XToys", {}),
        ("xtoys.toggle", "toggle", "Переключить устройство", {"device": _s("string")}),
        ("xtoys.set_intensity", "set_intensity", "Установить интенсивность", {"device": _s("string"), "value": _s("integer", minimum=0, maximum=100)}),
        ("xtoys.select_pattern", "select_pattern", "Выбрать паттерн", {"device": _s("string"), "pattern": _s("string")}),
        ("xtoys.get_status", "get_status", "Прочитать состояние XToys", {"device": _s("string")}),
        ("xtoys.motion_start", "motion_start", "Запустить Motion-to-Toy", {"region": _s("object")}),
        ("xtoys.motion_stop", "motion_stop", "Остановить Motion-to-Toy", {}),
        ("xtoys.motion_status", "motion_status", "Получить статус Motion-to-Toy", {}),
        ("xtoys.remote_session_start", "remote_session_start", "Открыть удалённую сессию", {"max_intensity": _s("number"), "ttl": _s("number")}),
        ("xtoys.remote_session_stop", "remote_session_stop", "Закрыть удалённую сессию", {}),
        ("xtoys.remote_status", "remote_status", "Получить статус удалённой сессии", {}),
        ("xtoys.emergency_stop", "emergency_stop", "Немедленно остановить XToys", {}),
    )
    required_by_action = {
        "set_intensity": ("value",), "select_pattern": ("pattern",),
        "motion_start": ("region",), "remote_session_start": ("max_intensity",),
    }
    for dotted, action, description, params in xtoys_specs:
        is_read = action in {"get_status", "motion_status", "remote_status"}
        _add(r, dotted, "xtoys", action, description, parameters=params,
             required=required_by_action.get(action, ()),
             permission=PermissionLevel.READ if is_read else PermissionLevel.CRITICAL,
             side_effect=not is_read, verification="device_state", expose=True)
    # Semantic operator actions are consumed by MissionExecutor, never ToolExecutor.
    _add(r, "operator.observe", "operator", "observe", "Получить свежую сцену",
         permission=PermissionLevel.READ, verification="fresh_scene")
    browser_params = {
        "inspect": ({"limit": _s("integer", minimum=1, maximum=200)}, (), False),
        "find": ({"limit": _s("integer", minimum=1, maximum=200)}, (), True),
        "read": ({}, (), True),
        "assert": ({"property": _s("string", enum=["value", "checked", "text", "name", "enabled"]),
                    "equals": {}}, ("property", "equals"), True),
        "wait": ({"milliseconds": _s("integer", minimum=0, maximum=5000)}, (), False),
        "click": ({}, (), True),
        "fill": ({"text": _s("string")}, ("text",), True),
        "press": ({"key": _s("string")}, ("key",), True),
        "select": ({"value": {}}, ("value",), True),
        "check": ({"checked": _s("boolean")}, (), True),
        "uncheck": ({}, (), True),
        "hover": ({}, (), True),
        "scroll": ({"delta_x": _s("integer"), "delta_y": _s("integer")}, (), False),
        "scroll_element": ({"delta_x": _s("integer"), "delta_y": _s("integer")}, (), True),
        "download": ({"path": _s("string")}, ("path",), True),
        "upload": ({"paths": _s("array", items=_s("string"))}, ("paths",), True),
    }
    browser_reads = {"inspect", "find", "read", "assert", "wait"}
    external_actions = {"click", "fill", "press", "select", "check", "uncheck", "upload"}
    for action, (params, required, needs_target) in browser_params.items():
        params = {**params, "scope": _s("object", description="Semantic role/name subtree or ref+snapshot_id; no selectors"),
                  "snapshot_id": _s("string"), "tab_id": _s("string")}
        if needs_target and action not in browser_reads:
            params["scroll_budget"] = _s("integer", minimum=0, maximum=2)
        perm = (PermissionLevel.READ if action in browser_reads else
                PermissionLevel.EXTERNAL_EFFECT if action in external_actions else PermissionLevel.LOCAL_REVERSIBLE)
        _add(r, f"operator.browser.{action}", "operator", f"browser_{action}",
             f"Semantic browser {action}", parameters=params, required=required,
             permission=perm, side_effect=action not in browser_reads, requires_target=needs_target,
             verification="explicit_postcondition")
        r.register_alias(f"browser.{action}", f"operator.browser.{action}")
        if action in {"click", "fill", "select", "check", "uncheck", "hover"}:
            r.register_alias(f"browser.{action}_ref", f"operator.browser.{action}")
            r.register_alias(f"operator.browser.{action}_ref", f"operator.browser.{action}")
    for action in ("new_tab", "switch_tab", "close_tab", "go_back", "go_forward"):
        params = {"url": _s("string")} if action == "new_tab" else (
            {"tab_id": _s("string")} if action in {"switch_tab", "close_tab"} else {})
        _add(r, f"operator.browser.{action}", "operator", f"browser_{action}",
             f"Browser tab action {action}", parameters=params,
             required=("tab_id",) if action in {"switch_tab", "close_tab"} else (),
             side_effect=True, verification="browser_location")
        r.register_alias(f"browser.{action}", f"operator.browser.{action}")
    desktop_params = {
        "inspect": ({}, (), False), "read": ({}, (), True),
        "click": ({}, (), True),
        "fill": ({"text": _s("string")}, ("text",), True),
        "press": ({"key": _s("string")}, ("key",), False),
        "check": ({}, (), True), "uncheck": ({}, (), True),
        "select": ({"value": {}}, ("value",), True),
        "focus": ({"app": _s("string")}, (), False),
        "launch": ({"app": _s("string")}, (), False),
    }
    for action, (params, required, needs_target) in desktop_params.items():
        _add(r, f"operator.desktop.{action}", "operator", f"desktop_{action}",
             f"Semantic desktop {action}", parameters=params, required=required,
             permission=PermissionLevel.READ if action in {"inspect", "read"} else PermissionLevel.LOCAL_REVERSIBLE,
             side_effect=action not in {"inspect", "read"}, physical_input=action in {"click", "fill", "press", "focus"},
             requires_target=needs_target, verification="explicit_postcondition")
    for action in ("read", "exists", "list"):
        _add(r, f"operator.file.{action}", "operator", f"file_{action}",
             f"Filesystem {action}", parameters={"path": _s("string")},
             required=("path",), permission=PermissionLevel.READ,
             verification="fresh_filesystem_read")
    file_write_specs = {
        "write_text": ({"path": _s("string"), "text": _s("string")}, ("path", "text")),
        "copy": ({"path": _s("string"), "destination": _s("string")}, ("path", "destination")),
        "move": ({"path": _s("string"), "destination": _s("string")}, ("path", "destination")),
        "mkdir": ({"path": _s("string")}, ("path",)),
    }
    for action, (params, required) in file_write_specs.items():
        _add(r, f"operator.file.{action}", "operator", f"file_{action}",
             f"Filesystem {action}", parameters=params, required=required,
             permission=PermissionLevel.LOCAL_REVERSIBLE, side_effect=True,
             verification="file_observation")
    _add(r, "operator.file.delete", "operator", "file_delete", "Delete a file or empty directory",
         parameters={"path": _s("string")}, required=("path",), permission=PermissionLevel.CRITICAL,
         side_effect=True, verification="file_absent")
    _add(r, "operator.wait", "operator", "wait", "Bounded wait",
         parameters={"seconds": _s("number", minimum=0, maximum=30)},
         permission=PermissionLevel.READ, verification="fresh_scene")
    return r


DEFAULT_ACTION_REGISTRY = build_default_registry()
