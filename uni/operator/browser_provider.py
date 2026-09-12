from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .action_registry import DEFAULT_ACTION_REGISTRY
from .browser_targeting import resolve_browser_element
from .models import BoundingBox, SceneSnapshot, TargetSpec, UIElement
from .targeting import TargetAmbiguous, TargetNotFound

__all__ = ["BrowserProvider", "TargetNotFound", "TargetAmbiguous"]


def _dom_element(raw: dict[str, Any]) -> UIElement:
    data = dict(raw)
    bbox = data.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0:
        data["bbox"] = BoundingBox(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
    elif not isinstance(bbox, dict):
        data["bbox"] = None
    allowed = {"ref", "source", "role", "name", "text", "bbox", "enabled",
               "value", "checked", "confidence", "metadata"}
    return UIElement.model_validate({key: value for key, value in data.items() if key in allowed})


class BrowserProvider:
    def __init__(self, session) -> None:
        self.session = session
        self._last_scene: SceneSnapshot | None = None
        self._last_action: dict[str, Any] | None = None
        self._operation_lock = asyncio.Lock()

    async def inspect(self, *, limit: int = 100, scope: dict[str, Any] | None = None) -> SceneSnapshot:
        kwargs: dict[str, Any] = {"limit": max(1, min(int(limit), 200))}
        if scope is not None:
            self._validate_scope(scope)
            kwargs["scope"] = scope
        raw = await self.session.operator_dom.inspect(**kwargs)
        browser = dict(raw.get("browser") or {})
        # Only adapter-owned receipts are authoritative, never page/model input.
        browser.pop("last_action", None)
        browser["snapshot_id"] = raw.get("snapshot_id")
        browser["timestamp"] = browser["observed_at"] = raw.get("timestamp")
        if self._last_action and browser.get("session_id") == self._last_action.get("session_id"):
            browser["last_action"] = deepcopy(self._last_action)
        scene = SceneSnapshot(
            snapshot_id=str(raw.get("snapshot_id") or ""),
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            active_window=raw.get("active_window") or {},
            windows=raw.get("windows") or [],
            browser=browser,
            elements=[_dom_element(item) for item in raw.get("elements") or []],
            evidence_refs=list(raw.get("evidence_refs") or []),
            errors=list(raw.get("errors") or []),
        )
        self._last_scene = scene
        return scene

    def resolve(self, target: TargetSpec, scene: SceneSnapshot) -> UIElement:
        return resolve_browser_element(target, scene)

    @staticmethod
    def _validate_scope(scope: dict[str, Any]) -> None:
        if not isinstance(scope, dict) or set(scope) - {"role", "name", "ref", "snapshot_id"}:
            raise ValueError("invalid_semantic_scope")
        if not any(scope.get(key) for key in ("role", "name", "ref")):
            raise ValueError("empty_semantic_scope")
        if scope.get("ref") and not scope.get("snapshot_id"):
            raise ValueError("scope_snapshot_id_required")

    async def _resolve_fresh(self, target: TargetSpec, params: dict[str, Any], *,
                             require_enabled: bool = True) -> tuple[SceneSnapshot, UIElement]:
        scope = params.get("scope")
        scene = await self.inspect(scope=scope)
        expected_tab = params.get("tab_id") or scene.browser.get("tab_id")
        expected_session = scene.browser.get("session_id")
        # Recovery happens only BEFORE any potentially external action. Never
        # replay a click after a timeout, or guess the new identity of a raw ref.
        budget = max(0, min(int(params.get("scroll_budget", 0)), 2))
        for attempt in range(budget + 1):
            if scene.errors:
                raise TargetNotFound("browser_observation_failed: " + ";".join(scene.errors))
            if ((expected_tab and scene.browser.get("tab_id") != expected_tab) or
                    scene.browser.get("session_id") != expected_session):
                raise ValueError("stale_ref: browser context changed during resolution")
            try:
                return scene, resolve_browser_element(target, scene, require_enabled=require_enabled)
            except TargetNotFound:
                if attempt == budget:
                    raise
            await self.session.operator_dom.act("scroll", snapshot_id=scene.snapshot_id, delta_y=600)
            scene = await self.inspect(scope=scope)
        raise TargetNotFound("target_not_found: retry budget exhausted")

    async def act(self, action: str, *, target: TargetSpec | None = None, **params: Any) -> dict[str, Any]:
        async with self._operation_lock:
            return await self._act(action, target=target, **params)

    async def _wait(self, target: TargetSpec | None, params: dict[str, Any]) -> dict[str, Any]:
        milliseconds = max(0, min(int(params.get("milliseconds", 250)), 5000))
        if target is None:
            await asyncio.sleep(milliseconds / 1000)
            scene = await self.inspect(scope=params.get("scope"))
            if scene.errors:
                raise ValueError("browser_observation_failed")
            return {**scene.model_dump(mode="json"), "status": "not_verified"}
        if target.ref:
            raise ValueError("wait_requires_semantic_target")
        deadline = asyncio.get_running_loop().time() + milliseconds / 1000
        identity = None
        while True:
            scene = await self.inspect(scope=params.get("scope"))
            current = (scene.browser.get("session_id"), scene.browser.get("tab_id"))
            if identity is None:
                identity = current
            if current != identity or (params.get("tab_id") and current[1] != params["tab_id"]):
                raise ValueError("stale_ref: tab changed while waiting")
            if scene.errors:
                raise ValueError("browser_observation_failed")
            try:
                element = resolve_browser_element(target, scene, require_enabled=False)
                return {"element": element.model_dump(mode="json"), "snapshot_id": scene.snapshot_id,
                        "browser": scene.browser, "status": "not_verified"}
            except TargetNotFound:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("browser_wait_timeout")
                await asyncio.sleep(min(0.1, remaining))

    async def _act(self, action: str, *, target: TargetSpec | None, **params: Any) -> dict[str, Any]:
        spec = DEFAULT_ACTION_REGISTRY.get(f"operator.browser.{action}")
        action = spec.name.removeprefix("operator.browser.")
        if set(params) - set(spec.parameters):
            raise ValueError("unsupported_browser_parameter")
        if any(name not in params for name in spec.required):
            raise ValueError("missing_browser_parameter")
        if params.get("scope") is not None:
            self._validate_scope(params["scope"])
        if spec.requires_target and target is None:
            raise ValueError("target_required")
        if target is not None and target.ref and not params.get("snapshot_id"):
            raise ValueError("snapshot_id_required: raw refs cannot be rebound")
        if action == "inspect":
            return (await self.inspect(limit=params.get("limit", 100), scope=params.get("scope"))).model_dump(mode="json")
        self._last_action = None
        if action == "wait":
            return await self._wait(target, params)
        element = None
        if target is not None and target.ref:
            scene = self._last_scene
            if scene is None or scene.snapshot_id != params["snapshot_id"]:
                raise ValueError("stale_ref")
            if params.get("tab_id") and params["tab_id"] != scene.browser.get("tab_id"):
                raise ValueError("stale_ref")
            element = resolve_browser_element(target, scene, require_enabled=action not in {"read", "find", "assert"})
        elif target is not None:
            scene, element = await self._resolve_fresh(target, params,
                                                       require_enabled=action not in {"read", "find", "assert"})
        else:
            scene = await self.inspect(scope=params.get("scope"))
        if action == "find":
            assert element is not None
            return {"element": element.model_dump(mode="json"), "snapshot_id": scene.snapshot_id,
                    "browser": scene.browser, "status": "not_verified"}
        started_at = datetime.now(timezone.utc).isoformat()
        receipt = {"id": uuid4().hex, "action": action, "started_at": started_at,
                   "session_id": scene.browser.get("session_id"),
                   "source_tab_id": scene.browser.get("tab_id"),
                   "before_snapshot_id": scene.snapshot_id,
                   "before_tabs": deepcopy(scene.browser.get("tabs", []))}
        mapping = {
            "click": "click_ref", "fill": "fill_ref", "press": "press",
            "select": "select_ref", "check": "check_ref", "hover": "hover_ref",
            "uncheck": "uncheck_ref", "scroll": "scroll", "scroll_element": "scroll_element",
            "download": "download", "upload": "upload", "read": "read", "assert": "assert", "wait": "wait",
        }
        if action in {"new_tab", "switch_tab", "close_tab"}:
            result = await self.session.change_tab(action, tab_id=str(params.get("tab_id", "")),
                                                    url=str(params.get("url", "")))
        elif action in {"go_back", "go_forward"}:
            result = await self.session.history(forward=action == "go_forward")
        else:
            call = {key: value for key, value in params.items()
                    if key not in {"scope", "tab_id", "scroll_budget", "limit"}}
            call["snapshot_id"] = scene.snapshot_id
            if element is not None:
                call["ref"] = element.ref
            if action == "check":
                call.setdefault("checked", True)
            result = await self.session.operator_dom.act(mapping[action], **call)
            if action == "assert" and result.get("assertion_passed") is not True:
                raise ValueError("browser_assertion_failed")
        receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
        for field in ("download_event", "file_observation"):
            if field in result:
                receipt[field] = deepcopy(result[field])
        self._last_action = receipt
        return {**result, "receipt": deepcopy(receipt), "status": "not_verified"}
