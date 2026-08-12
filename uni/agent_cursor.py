"""Visible agent cursor overlay (page-level) — does not steal the OS mouse.

Injects a labeled «UNI» pointer into the page via Playwright CDP/evaluate.
User system cursor stays independent; agent actions use DOM clicks.
"""

from __future__ import annotations

from typing import Any

# Injected once per page; idempotent.
_OVERLAY_JS = r"""
(() => {
  if (window.__UNI_CURSOR__) return true;
  const ROOT_ID = "uni-agent-cursor-root";
  let root = document.getElementById(ROOT_ID);
  if (!root) {
    root = document.createElement("div");
    root.id = ROOT_ID;
    root.setAttribute("data-uni", "agent-cursor");
    Object.assign(root.style, {
      position: "fixed",
      left: "0",
      top: "0",
      width: "0",
      height: "0",
      zIndex: "2147483646",
      pointerEvents: "none",
      display: "none",
    });
    const pointer = document.createElement("div");
    pointer.className = "uni-agent-pointer";
    Object.assign(pointer.style, {
      position: "fixed",
      width: "18px",
      height: "18px",
      marginLeft: "-3px",
      marginTop: "-3px",
      borderRadius: "50% 50% 50% 0",
      transform: "rotate(-45deg)",
      background: "linear-gradient(135deg, #6ee7ff, #a78bfa)",
      boxShadow: "0 0 0 2px rgba(6,16,24,0.85), 0 0 16px rgba(110,231,255,0.55)",
      transition: "left 0.22s ease-out, top 0.22s ease-out",
    });
    const label = document.createElement("div");
    label.className = "uni-agent-label";
    label.textContent = "UNI";
    Object.assign(label.style, {
      position: "fixed",
      transform: "translate(14px, 10px)",
      padding: "2px 7px",
      borderRadius: "6px",
      font: "600 11px/1.2 ui-sans-serif, system-ui, sans-serif",
      letterSpacing: "0.04em",
      color: "#061018",
      background: "linear-gradient(135deg, #6ee7ff, #c4b5fd)",
      boxShadow: "0 2px 10px rgba(0,0,0,0.35)",
      whiteSpace: "nowrap",
      transition: "left 0.22s ease-out, top 0.22s ease-out",
    });
    const ring = document.createElement("div");
    ring.className = "uni-agent-ring";
    Object.assign(ring.style, {
      position: "fixed",
      width: "28px",
      height: "28px",
      marginLeft: "-14px",
      marginTop: "-14px",
      borderRadius: "50%",
      border: "2px solid rgba(110,231,255,0.85)",
      opacity: "0",
      pointerEvents: "none",
      transition: "opacity 0.35s ease, transform 0.35s ease",
    });
    root.appendChild(ring);
    root.appendChild(pointer);
    root.appendChild(label);
    (document.documentElement || document.body).appendChild(root);
  }
  window.__UNI_CURSOR__ = {
    root,
    show(x, y, labelText) {
      const r = document.getElementById(ROOT_ID);
      if (!r) return;
      r.style.display = "block";
      const ptr = r.querySelector(".uni-agent-pointer");
      const lab = r.querySelector(".uni-agent-label");
      const ring = r.querySelector(".uni-agent-ring");
      if (ptr) { ptr.style.left = x + "px"; ptr.style.top = y + "px"; }
      if (lab) {
        lab.style.left = x + "px";
        lab.style.top = y + "px";
        if (labelText) lab.textContent = labelText;
      }
      if (ring) {
        ring.style.left = x + "px";
        ring.style.top = y + "px";
        ring.style.opacity = "0";
        ring.style.transform = "scale(0.6)";
      }
    },
    pulse(x, y) {
      const r = document.getElementById(ROOT_ID);
      if (!r) return;
      const ring = r.querySelector(".uni-agent-ring");
      if (!ring) return;
      ring.style.left = x + "px";
      ring.style.top = y + "px";
      ring.style.opacity = "1";
      ring.style.transform = "scale(1.4)";
      setTimeout(() => {
        ring.style.opacity = "0";
        ring.style.transform = "scale(0.6)";
      }, 280);
    },
    hide() {
      const r = document.getElementById(ROOT_ID);
      if (r) r.style.display = "none";
    },
  };
  return true;
})()
"""


class AgentCursorConfig:
    """Lightweight config object (also mirrored in BrowserConfig)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        label: str = "UNI",
        move_ms: int = 220,
        hide_after_ms: int = 1200,
    ) -> None:
        self.enabled = enabled
        self.label = label
        self.move_ms = move_ms
        self.hide_after_ms = hide_after_ms


async def ensure_overlay(page: Any) -> bool:
    """Install overlay on page if missing. Returns False on failure."""
    try:
        await page.evaluate(_OVERLAY_JS)
        return True
    except Exception:
        return False


async def install_on_context(context: Any) -> bool:
    """Install overlay on every new document in the browser context."""
    try:
        await context.add_init_script(_OVERLAY_JS)
        for page in list(getattr(context, "pages", []) or []):
            try:
                if not page.is_closed():
                    await page.evaluate(_OVERLAY_JS)
            except Exception:
                continue
        return True
    except Exception:
        return False


async def show_at(page: Any, x: float, y: float, *, label: str = "UNI") -> None:
    await ensure_overlay(page)
    try:
        await page.evaluate(
            """([x, y, label]) => {
              if (window.__UNI_CURSOR__) window.__UNI_CURSOR__.show(x, y, label);
            }""",
            [float(x), float(y), str(label)],
        )
    except Exception:
        pass


async def pulse_at(page: Any, x: float, y: float) -> None:
    try:
        await page.evaluate(
            """([x, y]) => {
              if (window.__UNI_CURSOR__) window.__UNI_CURSOR__.pulse(x, y);
            }""",
            [float(x), float(y)],
        )
    except Exception:
        pass


async def hide(page: Any) -> None:
    try:
        await page.evaluate(
            """() => { if (window.__UNI_CURSOR__) window.__UNI_CURSOR__.hide(); }"""
        )
    except Exception:
        pass


async def point_at_locator(
    page: Any,
    locator: Any,
    *,
    label: str = "UNI",
    move_ms: int = 220,
) -> tuple[float, float] | None:
    """Move overlay to center of locator. Returns viewport (x,y) or None."""
    try:
        box = await locator.bounding_box(timeout=5_000)
    except Exception:
        box = None
    if not box:
        return None
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    await show_at(page, x, y, label=label)
    # Allow CSS transition to play
    try:
        await page.wait_for_timeout(max(50, int(move_ms)))
    except Exception:
        pass
    return x, y


async def click_with_cursor(
    page: Any,
    locator: Any,
    *,
    label: str = "UNI",
    move_ms: int = 220,
    timeout: float = 10_000,
) -> None:
    """Show UNI cursor, pulse, then DOM click (OS mouse not moved)."""
    coords = await point_at_locator(page, locator, label=label, move_ms=move_ms)
    if coords:
        await pulse_at(page, coords[0], coords[1])
        try:
            await page.wait_for_timeout(80)
        except Exception:
            pass
    await locator.click(timeout=timeout)


async def fill_with_cursor(
    page: Any,
    locator: Any,
    text: str,
    *,
    label: str = "UNI",
    move_ms: int = 220,
    timeout: float = 10_000,
) -> None:
    coords = await point_at_locator(page, locator, label=label, move_ms=move_ms)
    if coords:
        await pulse_at(page, coords[0], coords[1])
    await locator.click(timeout=timeout)
    await locator.fill(text, timeout=timeout)
