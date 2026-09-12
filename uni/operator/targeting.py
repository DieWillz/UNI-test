from __future__ import annotations

from .models import SceneSnapshot, TargetSpec, UIElement


class TargetNotFound(LookupError):
    pass


class TargetAmbiguous(LookupError):
    pass


def _norm(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _source(value: object) -> str:
    return str(getattr(value, "value", value) or "").casefold()


def resolve_element(target: TargetSpec, scene: SceneSnapshot, *, source: str | None = None) -> UIElement:
    if target.ref:
        matches = [item for item in scene.elements if item.ref == target.ref]
        if len(matches) == 1:
            return matches[0]
        raise TargetNotFound(f"target_not_found: {target.ref}")

    wanted_source = _source(target.source) or _norm(source)
    wanted_role = _norm(target.role)
    wanted_name = _norm(target.name)
    wanted_text = _norm(target.text)
    scored: list[tuple[int, UIElement]] = []
    for item in scene.elements:
        if wanted_source and _source(item.source) != wanted_source:
            continue
        if wanted_role and _norm(item.role) != wanted_role:
            continue
        name, text = _norm(item.name), _norm(item.text)
        score = 0
        if target.exact:
            if wanted_name and name == wanted_name:
                score += 1000
            elif wanted_text and text == wanted_text:
                score += 900
            else:
                continue
        else:
            if wanted_name:
                if name == wanted_name:
                    score += 1000
                elif name.startswith(wanted_name):
                    score += 800
                elif wanted_name in name:
                    score += 700
            if wanted_text:
                if text == wanted_text:
                    score += 600
                elif wanted_text in text:
                    score += 500
            if score == 0:
                continue
        if wanted_role:
            score += 50
        if item.enabled:
            score += 10
        scored.append((score, item))

    if not scored:
        raise TargetNotFound("target_not_found")
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best = scored[0][0]
    winners = [item for score, item in scored if score == best]
    if len(winners) != 1:
        raise TargetAmbiguous(f"ambiguous_target: {len(winners)} candidates")
    return winners[0]
