from __future__ import annotations

import asyncio
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from uni.contracts import Evidence, Verification, VerificationStatus

from .action_registry import DEFAULT_ACTION_REGISTRY
from .browser_targeting import resolve_browser_element
from .models import PlanStep, SceneSnapshot, TargetSpec
from .targeting import TargetAmbiguous, TargetNotFound, resolve_element


class PostconditionVerifier:
    """Verifies a step from a fresh observation, never from action success alone."""

    def __init__(self, *, file_provider=None) -> None:
        self.file_provider = file_provider

    @staticmethod
    def _verified(source: str, summary: str, data: Any, method: str) -> Verification:
        evidence = Evidence(source=source, summary=summary, data=data)
        return Verification(
            status=VerificationStatus.VERIFIED,
            method=method,
            reason=summary,
            evidence=[evidence],
            verifier="uni.operator.verifier",
        )

    @staticmethod
    def _not_verified(reason: str) -> Verification:
        return Verification(
            status=VerificationStatus.NOT_VERIFIED,
            method="postcondition",
            reason=reason,
            evidence=[],
            verifier="uni.operator.verifier",
        )
    async def verify(self, step: PlanStep, *, scene: SceneSnapshot) -> Verification:
        condition = step.postcondition
        if condition is None:
            return self._not_verified("step_has_no_postcondition")
        kind, params = condition.kind, condition.params
        if kind.startswith("browser."):
            return await self._verify_browser(kind, params, step, scene)
        if kind.startswith("window."):
            return self._verify_window(kind, params, scene)
        if kind.startswith("element."):
            if self._canonical_action(step).startswith(("browser.", "operator.browser.")):
                return await self._verify_browser(f"browser.{kind}", params, step, scene)
            return self._verify_element(kind, params, step, scene)
        if kind.startswith("file."):
            return await self._verify_file(kind, params)
        return self._not_verified(f"unsupported_postcondition: {kind}")

    @staticmethod
    def _canonical_action(step: PlanStep) -> str:
        try:
            return DEFAULT_ACTION_REGISTRY.get(step.action).name
        except KeyError:
            return step.action

    @staticmethod
    def _browser_time(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    def _browser_context_error(self, step: PlanStep, scene: SceneSnapshot) -> str:
        browser = scene.browser
        if any(not isinstance(browser.get(key), str) or not browser[key].strip()
               for key in ("session_id", "tab_id", "snapshot_id")):
            return "browser_observation_scope_missing"
        observed = self._browser_time(browser.get("observed_at"))
        scene_time = self._browser_time(scene.timestamp)
        if observed is None or scene_time is None:
            return "browser_observation_timestamp_missing"
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < -1 or age > 30 or scene_time < observed:
            return "browser_observation_stale"
        # UIA or visual fallback failures do not invalidate an independent DOM read.
        if any(not str(error).casefold().startswith(("uia", "window", "ocr", "vision"))
               for error in scene.errors):
            return "browser_observation_failed"
        receipt = browser.get("last_action")
        if receipt is not None:
            if not isinstance(receipt, dict) or not receipt.get("id"):
                return "browser_action_receipt_invalid"
            started = self._browser_time(receipt.get("started_at"))
            completed = self._browser_time(receipt.get("completed_at"))
            if started is None or completed is None or not started <= completed <= observed:
                return "browser_observation_precedes_action"
            if (observed - completed).total_seconds() > 30:
                return "browser_action_receipt_stale"
            if receipt.get("session_id") != browser["session_id"]:
                return "browser_action_session_mismatch"
            action = self._canonical_action(step).rsplit(".", 1)[-1]
            if receipt.get("action") != action:
                return "browser_action_receipt_mismatch"
            if not receipt.get("before_snapshot_id") or receipt["before_snapshot_id"] == browser["snapshot_id"]:
                return "browser_snapshot_not_refreshed"
            popup_condition = step.postcondition is not None and step.postcondition.kind == "browser.tab_appeared"
            if (action not in {"new_tab", "switch_tab", "close_tab"} and not popup_condition
                    and receipt.get("source_tab_id") != browser["tab_id"]):
                return "browser_action_tab_mismatch"
        return ""

    @staticmethod
    def _browser_evidence(scene: SceneSnapshot) -> dict[str, Any]:
        return {key: scene.browser.get(key) for key in
                ("session_id", "tab_id", "snapshot_id", "observed_at")}

    async def _verify_browser(self, kind: str, params: dict[str, Any], step: PlanStep,
                              scene: SceneSnapshot) -> Verification:
        error = self._browser_context_error(step, scene)
        if error:
            return self._not_verified(error)
        browser = scene.browser
        expected_session = params.get("session_id", step.params.get("session_id"))
        if expected_session is not None and expected_session != browser.get("session_id"):
            return self._not_verified("browser_session_id_mismatch")
        if kind in {"browser.tab_appeared", "browser.tab_disappeared"}:
            return self._verify_browser_tabs(kind, params, scene)
        for key in ("session_id", "tab_id"):
            expected_scope = params.get(key, step.params.get(key))
            if expected_scope is not None and expected_scope != browser.get(key):
                return self._not_verified(f"browser_{key}_mismatch")
        if kind == "browser.download_completed":
            return await self._verify_browser_download(params, step, scene)
        if kind.startswith("browser.element."):
            return self._verify_browser_element(kind, params, step, scene)
        if kind not in {"browser.url_equals", "browser.url_contains",
                        "browser.title_equals", "browser.title_contains"}:
            return self._not_verified(f"unsupported_browser_postcondition: {kind}")
        field = kind.removeprefix("browser.").split("_", 1)[0]
        actual = browser.get(field)
        expected = params.get("text" if kind.endswith("contains") else "value")
        if not isinstance(expected, str) or not expected or not isinstance(actual, str):
            return self._not_verified(f"browser_{field}_expectation_missing")
        matched = expected.casefold() in actual.casefold() if kind.endswith("contains") else actual == expected
        if not matched:
            return self._not_verified(f"browser_{field}_mismatch")
        return self._verified("browser", f"fresh browser {field} matched",
                              {**self._browser_evidence(scene), "observed": actual, "expected": expected}, kind)

    def _verify_browser_element(self, kind: str, params: dict[str, Any], step: PlanStep,
                                scene: SceneSnapshot) -> Verification:
        predicate = kind.removeprefix("browser.element.")
        if predicate not in {"exists", "missing", "enabled", "disabled", "checked", "unchecked",
                             "text_contains", "text_equals", "value_contains", "value_equals",
                             "checked_equals", "enabled_equals"}:
            return self._not_verified(f"unsupported_browser_element_postcondition: {kind}")
        try:
            target = TargetSpec.model_validate(params["target"]) if "target" in params else step.target
        except (TypeError, ValueError):
            return self._not_verified("browser_postcondition_target_invalid")
        if target is None:
            return self._not_verified("browser_element_postcondition_requires_target")
        if getattr(target.source, "value", target.source) not in {None, "", "dom"}:
            return self._not_verified("browser_element_requires_dom_target")
        if not (target.name.strip() or target.text.strip()):
            return self._not_verified("browser_postcondition_requires_semantic_target")
        # Opaque refs can be recycled in the next snapshot. Postconditions resolve
        # semantic identity anew, even when an action carried a bound raw ref.
        target = target.model_copy(update={"ref": ""})
        missing = predicate == "missing"
        if missing:
            if scene.browser.get("elements_complete") is not True or scene.browser.get("complete") is not True:
                return self._not_verified("browser_elements_observation_incomplete")
        try:
            element = resolve_browser_element(target, scene, require_enabled=False)
        except TargetAmbiguous as exc:
            return self._not_verified(str(exc))
        except TargetNotFound as exc:
            if missing:
                return self._verified("browser.dom", "fresh complete DOM confirms semantic target absence",
                                      {**self._browser_evidence(scene),
                                       "target": target.model_dump(mode="json"), "exists": False}, kind)
            return self._not_verified(str(exc))
        except (TypeError, ValueError) as exc:
            return self._not_verified(f"browser_target_invalid: {exc}")
        if getattr(element.source, "value", element.source) != "dom":
            return self._not_verified("browser_element_source_mismatch")
        for key in ("session_id", "tab_id", "snapshot_id"):
            if key in element.metadata and element.metadata[key] != scene.browser.get(key):
                return self._not_verified(f"browser_element_{key}_mismatch")
        if missing:
            return self._not_verified("browser_element_still_exists")
        evidence = {**self._browser_evidence(scene), "ref": element.ref}
        if predicate == "exists":
            return self._verified("browser.dom", "fresh scoped DOM target exists", evidence, kind)
        if predicate in {"enabled", "disabled", "checked", "unchecked"}:
            field = "enabled" if predicate in {"enabled", "disabled"} else "checked"
            expected = predicate in {"enabled", "checked"}
        else:
            field = predicate.rsplit("_", 1)[0]
            expected = params.get("text", params.get("value")) if predicate.endswith("contains") else params.get("value")
            if expected is None:
                return self._not_verified("browser_element_expectation_missing")
        if field not in element.model_fields_set:
            return self._not_verified(f"browser_element_{field}_not_observed")
        actual = getattr(element, field)
        if predicate.endswith("contains"):
            matched = isinstance(actual, str) and isinstance(expected, str) and bool(expected) and expected.casefold() in actual.casefold()
        else:
            matched = type(actual) is type(expected) and actual == expected
        if not matched:
            return self._not_verified(f"browser_element_{field}_mismatch")
        return self._verified("browser.dom", f"fresh scoped DOM {field} matched",
                              {**evidence, "observed": actual, "expected": expected}, kind)

    def _verify_browser_tabs(self, kind: str, params: dict[str, Any], scene: SceneSnapshot) -> Verification:
        browser = scene.browser
        receipt = browser.get("last_action")
        if (not isinstance(receipt, dict) or browser.get("tabs_complete") is not True
                or browser.get("complete") is not True):
            return self._not_verified("browser_tabs_transition_evidence_missing")
        before, after = receipt.get("before_tabs"), browser.get("tabs")
        if not isinstance(before, list) or not isinstance(after, list):
            return self._not_verified("browser_tabs_observation_incomplete")
        if any(not isinstance(tab, dict) or not isinstance(tab.get("tab_id"), str) or not tab["tab_id"]
               for tab in [*before, *after]):
            return self._not_verified("browser_tabs_scope_missing")
        before_ids, after_ids = {tab["tab_id"] for tab in before}, {tab["tab_id"] for tab in after}
        if receipt.get("source_tab_id") not in before_ids:
            return self._not_verified("browser_tabs_source_missing_from_baseline")
        if len(before_ids) != len(before) or len(after_ids) != len(after):
            return self._not_verified("browser_tabs_identity_ambiguous")
        selectors = {key: params[key] for key in ("tab_id", "url", "title") if key in params}
        if any(not isinstance(value, str) or not value for value in selectors.values()):
            return self._not_verified("browser_tab_expectation_invalid")
        appeared = kind == "browser.tab_appeared"
        changed = after_ids - before_ids if appeared else before_ids - after_ids
        candidates = [tab for tab in (after if appeared else before) if tab["tab_id"] in changed
                      and all(tab.get(key) == value for key, value in selectors.items())]
        if len(candidates) != 1:
            return self._not_verified("browser_tab_transition_missing_or_ambiguous")
        return self._verified("browser.tabs", "fresh scoped tab transition observed",
                              {**self._browser_evidence(scene), "receipt_id": receipt["id"],
                               "before_tab_ids": sorted(before_ids), "after_tab_ids": sorted(after_ids),
                               "changed_tab": candidates[0]}, kind)

    async def _verify_browser_download(self, params: dict[str, Any], step: PlanStep,
                                       scene: SceneSnapshot) -> Verification:
        receipt = scene.browser.get("last_action")
        if self._canonical_action(step).rsplit(".", 1)[-1] != "download" or not isinstance(receipt, dict):
            return self._not_verified("browser_download_receipt_missing")
        event, observed_file = receipt.get("download_event"), receipt.get("file_observation")
        if (not isinstance(event, dict) or "failure" not in event or event["failure"] is not None
                or not isinstance(event.get("url"), str) or not event["url"]
                or not isinstance(observed_file, dict)):
            return self._not_verified("browser_download_event_missing_or_failed")
        file_time = self._browser_time(observed_file.get("observed_at"))
        started = self._browser_time(receipt.get("started_at"))
        observed = self._browser_time(scene.browser.get("observed_at"))
        if file_time is None or started is None or observed is None or not started <= file_time <= observed:
            return self._not_verified("browser_download_file_observation_stale")
        values = [params.get("path"), step.params.get("path"), observed_file.get("path")]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            return self._not_verified("browser_download_path_required")
        try:
            paths = [Path(value) for value in values]
            if any(not path.is_absolute() for path in paths):
                return self._not_verified("browser_download_absolute_path_required")
            expected, requested, actual_path = [path.resolve() for path in paths]
            if expected != requested or expected != actual_path:
                return self._not_verified("browser_download_path_mismatch")
            fresh = await asyncio.to_thread(actual_path.stat)
        except (OSError, ValueError, RuntimeError) as exc:
            return self._not_verified(f"browser_download_stat_failed: {exc}")
        if (not stat.S_ISREG(fresh.st_mode) or fresh.st_size <= 0
                or type(observed_file.get("size")) is not int
                or type(observed_file.get("mtime_ns")) is not int
                or fresh.st_size != observed_file["size"] or fresh.st_mtime_ns != observed_file["mtime_ns"]):
            return self._not_verified("browser_download_file_not_completed_or_changed")
        return self._verified("browser.download+filesystem", "browser download event corroborated by independent fresh file stat",
                              {**self._browser_evidence(scene), "receipt_id": receipt["id"],
                               "download_event": event, "path": str(actual_path), "size": fresh.st_size,
                               "mtime_ns": fresh.st_mtime_ns, "stat_observed_at": datetime.now(timezone.utc).isoformat()},
                              "browser.download_completed")

    def _verify_window(self, kind: str, params: dict[str, Any], scene: SceneSnapshot) -> Verification:
        actual = str((scene.active_window or {}).get("title") or "")
        expected = str(params.get("text") if kind.endswith("contains") else params.get("value") or "")
        if kind == "window.title_contains":
            matched = bool(expected) and expected.casefold() in actual.casefold()
        elif kind == "window.title_equals":
            matched = actual == expected
        else:
            return self._not_verified(f"unsupported_window_postcondition: {kind}")
        if not matched:
            return self._not_verified("window_title_mismatch")
        return self._verified("uia", "fresh active window matched",
                              {"observed": actual, "expected": expected, "snapshot_id": scene.snapshot_id}, kind)

    def _verify_element(self, kind: str, params: dict[str, Any], step: PlanStep,
                        scene: SceneSnapshot) -> Verification:
        if step.target is None:
            return self._not_verified("element_postcondition_requires_target")
        try:
            element = resolve_element(step.target, scene)
        except (TargetNotFound, TargetAmbiguous) as exc:
            return self._not_verified(str(exc))
        if kind == "element.exists":
            return self._verified(str(element.source), "fresh semantic target exists",
                                  {"ref": element.ref, "snapshot_id": scene.snapshot_id}, kind)
        field = kind.split(".", 1)[1].rsplit("_", 1)[0]
        actual = getattr(element, field, None)
        expected = params.get("value")
        if kind.endswith("contains"):
            expected = params.get("text", expected)
            matched = bool(str(expected)) and str(expected).casefold() in str(actual or "").casefold()
        elif kind.endswith("equals"):
            matched = type(actual) is type(expected) and actual == expected
        else:
            return self._not_verified(f"unsupported_element_postcondition: {kind}")
        if not matched:
            return self._not_verified(f"element_{field}_mismatch")
        return self._verified(str(element.source), f"fresh element {field} matched",
                              {"ref": element.ref, "observed": actual, "expected": expected,
                               "snapshot_id": scene.snapshot_id}, kind)
    async def _verify_file(self, kind: str, params: dict[str, Any]) -> Verification:
        if self.file_provider is None:
            return self._not_verified("filesystem_verifier_unavailable")
        path = str(params.get("path") or "")
        if not path:
            return self._not_verified("file_postcondition_requires_path")
        exists = await self.file_provider.act("exists", path=path)
        if kind == "file.absent":
            if exists.get("exists") is False:
                return self._verified("filesystem", "fresh filesystem check confirms absence",
                                      exists, kind)
            return self._not_verified("file_still_exists")
        if exists.get("exists") is not True:
            return self._not_verified("file_missing")
        if kind == "file.exists":
            return self._verified("filesystem", "fresh filesystem check confirms file",
                                  exists, kind)
        if kind in {"file.text_contains", "file.text_equals"}:
            try:
                read = await self.file_provider.act("read", path=path)
            except Exception as exc:
                return self._not_verified(f"file_read_failed: {exc}")
            actual = str(read.get("text") or "")
            expected = str(params.get("text") or "")
            matched = expected in actual if kind.endswith("contains") else actual == expected
            if not matched:
                return self._not_verified("file_text_mismatch")
            safe = {key: read.get(key) for key in ("path", "size", "mtime_ns", "sha256", "truncated")}
            safe["matched_text"] = expected[:500]
            return self._verified("filesystem", "fresh file content matched", safe, kind)
        return self._not_verified(f"unsupported_file_postcondition: {kind}")
