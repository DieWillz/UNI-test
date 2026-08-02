"""Desktop action badge — always-on-top indicator next to pyautogui clicks.

Not a second OS mouse (Windows has one system cursor). Shows a short-lived
label «UNI» near the point where the agent moves/clicks so the user sees
agent activity without confusing it with their own intent.

Uses stdlib tkinter only (ships with official Windows Python builds).
Safe no-op if tkinter/display is unavailable (servers, headless CI).
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional


class UniActionBadge:
    def __init__(
        self,
        *,
        enabled: bool = True,
        label: str = "UNI",
        duration_ms: int = 450,
        offset_x: int = 18,
        offset_y: int = 18,
    ) -> None:
        self.enabled = enabled
        self.label = label
        self.duration_ms = max(100, int(duration_ms))
        self.offset_x = int(offset_x)
        self.offset_y = int(offset_y)
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
        # Borderless, always on top, try click-through where supported
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
            overlay.attributes("-alpha", 0.92)
        except Exception:
            pass

        frame = tk.Frame(overlay, bg="#6ee7ff", padx=1, pady=1)
        frame.pack()
        inner = tk.Frame(frame, bg="#0b1220", padx=8, pady=4)
        inner.pack()
        text_var = tk.StringVar(value=self.label)
        lbl = tk.Label(
            inner,
            textvariable=text_var,
            fg="#6ee7ff",
            bg="#0b1220",
            font=("Segoe UI", 10, "bold"),
        )
        lbl.pack()
        sub = tk.Label(
            inner,
            text="agent",
            fg="#94a3b8",
            bg="#0b1220",
            font=("Segoe UI", 8),
        )
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
            text_var.set(f"{self.label} · {action}" if action else self.label)
            try:
                overlay.geometry(f"+{max(0, x + self.offset_x)}+{max(0, y + self.offset_y)}")
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
        """Show badge near screen coordinates (non-blocking)."""
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
