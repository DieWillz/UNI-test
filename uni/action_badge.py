"""Desktop action badge — always-on-top indicator next to mouse actions.

Not a second OS mouse (Windows has one system cursor). Shows a short-lived
lime ring (#B8E61D) at the click point PLUS a small «Юни» label so the user
always sees that Юни (not the user) is driving the mouse. This is the required
visual signature from директива «Мышь Юни» (2026-08-13).

Uses stdlib tkinter only (ships with official Windows Python builds).
Safe no-op if tkinter/display is unavailable (servers, headless CI).
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

# Лайм-кольцо «Юни» (директива: #B8E61D)
UNI_LIME = "#B8E61D"
UNI_LABEL = "Юни"


class UniActionBadge:
    def __init__(
        self,
        *,
        enabled: bool = True,
        label: str = UNI_LABEL,
        duration_ms: int = 600,
        offset_x: int = 20,
        offset_y: int = 20,
        ring_color: str = UNI_LIME,
    ) -> None:
        self.enabled = enabled
        self.label = label
        self.duration_ms = max(100, int(duration_ms))
        self.offset_x = int(offset_x)
        self.offset_y = int(offset_y)
        self.ring_color = ring_color
        self._q: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._failed = False

    def _ensure_thread(self) -> bool:
        if self._failed or not self.enabled:
            return False
        if self._started and self._thread and self._thread.is_alive():
            return True
        try:
            import tkinter  # noqa: F401
        except Exception:
            self._failed = True
            return False
        self._thread = threading.Thread(target=self._run, name="uni-action-badge", daemon=True)
        self._thread.start()
        self._started = True
        return True

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            self._failed = True
            return

        root = tk.Tk()
        root.withdraw()
        overlay = tk.Toplevel(root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        try:
            overlay.attributes("-topmost", True)
        except Exception:
            pass
        try:
            # Windows: transparent color key for faux click-through look
            overlay.attributes("-transparentcolor", "#010101")
            overlay.configure(bg="#010101")
        except Exception:
            overlay.configure(bg="#111111")
        try:
            overlay.attributes("-alpha", 0.95)
        except Exception:
            pass

        # --- лайм-кольцо (Canvas) + бейдж «Юни» под ним ---
        canvas = tk.Canvas(overlay, width=120, height=120, bg="#010101",
                           highlightthickness=0, bd=0)
        canvas.pack()
        # кольцо вокруг точки (центр ~ (40,40)); сама точка клика — в (40,40)
        ring = canvas.create_oval(8, 8, 72, 72, outline=self.ring_color, width=4)
        dot = canvas.create_oval(36, 36, 44, 44, fill=self.ring_color, outline="")
        # бейдж «Юни» — метка у курсора во время движения
        frame = tk.Frame(overlay, bg="#010101")
        frame.place(x=46, y=46)
        inner = tk.Frame(frame, bg="#0b1220", padx=8, pady=4)
        inner.pack()
        lbl = tk.Label(inner, text=self.label, fg=self.ring_color,
                       bg="#0b1220", font=("Segoe UI", 10, "bold"))
        lbl.pack()
        sub = tk.Label(inner, text="водит мышью", fg="#94a3b8",
                       bg="#0b1220", font=("Segoe UI", 8))
        sub.pack()

        hide_after_id: list = []

        def hide() -> None:
            try:
                overlay.withdraw()
            except Exception:
                pass

        def show_at(x: int, y: int, action: str) -> None:
            for hid in hide_after_id:
                try:
                    root.after_cancel(hid)
                except Exception:
                    pass
            hide_after_id.clear()
            try:
                overlay.geometry(f"+{max(0, x - 40)}+{max(0, y - 40)}")
                overlay.deiconify()
                overlay.lift()
            except Exception:
                return
            hide_after_id.append(root.after(self.duration_ms, hide))

        def pump() -> None:
            try:
                while True:
                    item = self._q.get_nowait()
                    if item is None:
                        try:
                            root.destroy()
                        except Exception:
                            pass
                        return
                    x, y, action = item
                    show_at(int(x), int(y), str(action or "click"))
            except queue.Empty:
                pass
            root.after(50, pump)

        root.after(50, pump)
        try:
            root.mainloop()
        except Exception:
            self._failed = True

    def flash_at(self, x: int, y: int, action: str = "click") -> None:
        """Show lime ring + «Юни» badge near screen coordinates (non-blocking)."""
        if not self.enabled:
            return
        if not self._ensure_thread():
            return
        try:
            self._q.put_nowait((int(x), int(y), action))
        except Exception:
            pass

    def close(self) -> None:
        if not self._started:
            return
        try:
            self._q.put_nowait(None)
        except Exception:
            pass


# Module-level singleton optional helpers for call sites that lack ComputerCapability
_default_badge: Optional[UniActionBadge] = None


def get_default_badge() -> UniActionBadge:
    global _default_badge
    if _default_badge is None:
        _default_badge = UniActionBadge()
    return _default_badge


def flash(x: int, y: int, action: str = "click") -> None:
    get_default_badge().flash_at(x, y, action)
