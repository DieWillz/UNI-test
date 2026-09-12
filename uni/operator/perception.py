from __future__ import annotations

import asyncio
from typing import Any, Callable
from uni.tools.executors import ToolExecutor

from .models import BoundingBox, SceneSnapshot, TargetSpec, UIElement
from .targeting import TargetAmbiguous, TargetNotFound

# OCR-провайдер (uni/tools/local_vision_fallback.ocr_find_text) детерминированно
# возвращает confidence 0.7 для найденного текста; порог должен пропускать его,
# иначе Tier-0 OCR никогда не срабатывает и всё уходит в VLM fallback.
_OCR_MIN_CONFIDENCE = 0.7


class PerceptionBroker:
    """Structured-first perception: DOM -> UIA -> OCR -> VLM."""

    def __init__(self, browser, windows, *, vision=None,
                 ocr_finder: Callable[[str], dict[str, Any] | None] | None = None) -> None:
        self.browser = browser
        self.windows = windows
        self.vision = vision
        self.ocr_finder = ocr_finder if ocr_finder is not None else self._default_ocr

    @staticmethod
    def _default_ocr(text: str) -> dict[str, Any] | None:
        try:
            from uni.tools.local_vision_fallback import ocr_find_text
            return ocr_find_text(text)
        except Exception:
            return None

    async def observe(self) -> SceneSnapshot:
        if ToolExecutor.mouse_only():
            # An existing browser window is a Windows surface, not a CDP session.
            return await self.windows.inspect()
        browser_result, windows_result = await asyncio.gather(
            self.browser.inspect(), self.windows.inspect(), return_exceptions=True,
        )
        b = browser_result if isinstance(browser_result, SceneSnapshot) else SceneSnapshot(errors=["dom_unavailable"])
        w = windows_result if isinstance(windows_result, SceneSnapshot) else SceneSnapshot(errors=["uia_unavailable"])
        return SceneSnapshot(
            active_window=w.active_window, windows=w.windows, browser=b.browser,
            elements=[*b.elements, *w.elements],
            evidence_refs=[*b.evidence_refs, *w.evidence_refs],
            errors=[*b.errors, *w.errors],
        )

    @staticmethod
    def _fallback_element(raw: dict[str, Any], source: str, description: str) -> UIElement:
        width, height = float(raw.get("width") or 0), float(raw.get("height") or 0)
        if width <= 0 or height <= 0:
            raise TargetNotFound(f"{source}_target_has_no_bbox")
        return UIElement(
            ref=f"{source}-transient", source=source, role="unknown",
            name=description, text=description,
            bbox=BoundingBox(x=float(raw.get("x") or 0), y=float(raw.get("y") or 0),
                             width=width, height=height),
            confidence=float(raw.get("confidence") or 0.5), metadata={"transient": True},
        )

    async def resolve_desktop(self, target: TargetSpec) -> UIElement:
        scene = await self.windows.inspect()
        try:
            return self.windows.resolve(target, scene)
        except TargetNotFound:
            if target.ref:
                raise
        description = target.name or target.text or target.role
        if not description:
            raise TargetNotFound("target_not_found")
        try:
            raw = await asyncio.to_thread(self.ocr_finder, description)
        except Exception:
            raw = None
        # A weak OCR candidate must not prevent the independent vision fallback.
        if raw and float(raw.get("confidence") or 0) >= _OCR_MIN_CONFIDENCE:
            return self._fallback_element(raw, "ocr", description)
        if self.vision is None:
            raise TargetNotFound("target_not_found")
        result = await self.vision.execute("find_desktop_element", description=description)
        if not getattr(result, "success", False) or not isinstance(result.data, dict):
            raise TargetNotFound("target_not_found")
        return self._fallback_element(result.data, "vision", description)
