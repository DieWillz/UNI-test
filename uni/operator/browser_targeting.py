"""DOM-only semantic ranking. Ambiguity is an error, not an invitation to click."""
from __future__ import annotations

from .models import SceneSnapshot, TargetSpec, UIElement
from .targeting import TargetAmbiguous, TargetNotFound


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _rank(wanted: str, name: str, text: str, exact: bool) -> int:
    if wanted == name:
        return 100
    if wanted == text:
        return 90
    needle, normalized_name, normalized_text = _norm(wanted), _norm(name), _norm(text)
    if needle in {normalized_name, normalized_text}:
        return 80
    if exact:
        return 0
    if normalized_name.startswith(needle) or normalized_text.startswith(needle):
        return 60
    return 40 if needle in normalized_name or needle in normalized_text else 0


def resolve_browser_element(target: TargetSpec, scene: SceneSnapshot, *,
                            require_enabled: bool = True) -> UIElement:
    source = str(getattr(target.source, "value", target.source) or "dom")
    if source != "dom":
        raise TargetNotFound("target_not_found: not a DOM target")
    scored: list[tuple[int, UIElement]] = []
    for element in scene.elements:
        if str(getattr(element.source, "value", element.source)) != "dom":
            continue
        if element.metadata.get("visible") is False or (require_enabled and not element.enabled):
            continue
        if scene.browser.get("active_dialog") and not element.metadata.get("in_dialog"):
            continue
        if target.ref and element.ref != target.ref:
            continue
        if target.role and _norm(target.role) != _norm(element.role):
            continue
        scores = []
        if target.name:
            scores.append(_rank(target.name, element.name, element.text, target.exact))
        if target.text:
            scores.append(_rank(target.text, element.text, element.text, target.exact))
        if any(score == 0 for score in scores):
            continue
        if not target.ref and not scores:
            continue
        scored.append((sum(scores) or 100, element))
    if not scored:
        raise TargetNotFound("target_not_found: no enabled visible semantic match" if require_enabled
                             else "target_not_found: no visible semantic match")
    best = max(score for score, _ in scored)
    winners = [item for score, item in scored if score == best]
    if len(winners) != 1:
        raise TargetAmbiguous(f"ambiguous_target: {len(winners)} candidates")
    return winners[0]
