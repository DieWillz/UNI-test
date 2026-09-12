"""Process-lifetime desktop badge for UNI mouse actions.

Tkinter is deliberately hosted by one daemon worker for the whole process.
Destroying a Tcl interpreter created on a background thread can crash CPython
on Windows during teardown (``Tcl_AsyncDelete``), so individual badge facades
never own or destroy the shared interpreter.
"""
from __future__ import annotations

import queue
import threading
from typing import Any, Optional

UNI_LIME = "#B8E61D"
UNI_LABEL = "Юни"


class _BadgeWorker:
    """One bounded, process-lifetime Tk worker shared by all badge facades."""

    def __init__(self) -> None:
        self._q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._failed = False

    def ensure_started(self) -> bool:
        if self._failed:
            return False
        thread = self._thread
        if thread is not None and thread.is_alive():
            return True
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return True
            try:
                import tkinter  # noqa: F401
            except Exception:
                self._failed = True
                return False
            self._thread = threading.Thread(
                target=self._run,
                name="uni-action-badge",
                daemon=True,
            )
            self._thread.start()
            return True

    def post(self, item: dict[str, Any]) -> bool:
        if not self.ensure_started():
            return False
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            return False

    def _run(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception:
            self._failed = True
            return
        root.withdraw()
        overlay = tk.Toplevel(root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        try:
            overlay.attributes("-topmost", True)
        except Exception:
            pass
        try:
            overlay.attributes("-transparentcolor", "#010101")
            overlay.configure(bg="#010101")
        except Exception:
            overlay.configure(bg="#111111")
        try:
            overlay.attributes("-alpha", 0.95)
        except Exception:
            pass

        canvas = tk.Canvas(
            overlay, width=120, height=120, bg="#010101",
            highlightthickness=0, bd=0,
        )
        canvas.pack()
        ring = canvas.create_oval(8, 8, 72, 72, outline=UNI_LIME, width=4)
        dot = canvas.create_oval(36, 36, 44, 44, fill=UNI_LIME, outline="")
        frame = tk.Frame(overlay, bg="#010101")
        frame.place(x=46, y=46)
        inner = tk.Frame(frame, bg="#0b1220", padx=8, pady=4)
        inner.pack()
        label = tk.Label(
            inner, text=UNI_LABEL, fg=UNI_LIME, bg="#0b1220",
            font=("Segoe UI", 10, "bold"),
        )
        label.pack()
        tk.Label(
            inner, text="водит мышью", fg="#94a3b8", bg="#0b1220",
            font=("Segoe UI", 8),
        ).pack()
        hide_after_id: list[str] = []

        def hide() -> None:
            try:
                overlay.withdraw()
            except Exception:
                pass

        def show(item: dict[str, Any]) -> None:
            for handle in hide_after_id:
                try:
                    root.after_cancel(handle)
                except Exception:
                    pass
            hide_after_id.clear()
            color = str(item.get("ring_color") or UNI_LIME)
            canvas.itemconfigure(ring, outline=color)
            canvas.itemconfigure(dot, fill=color)
            label.configure(text=str(item.get("label") or UNI_LABEL), fg=color)
            x = int(item.get("x") or 0)
            y = int(item.get("y") or 0)
            offset_x = int(item.get("offset_x") or 20)
            offset_y = int(item.get("offset_y") or 20)
            try:
                overlay.geometry(f"+{max(0, x - offset_x - 20)}+{max(0, y - offset_y - 20)}")
                overlay.deiconify()
                overlay.lift()
            except Exception:
                return
            duration = max(100, int(item.get("duration_ms") or 600))
            hide_after_id.append(root.after(duration, hide))

        def pump() -> None:
            try:
                while True:
                    show(self._q.get_nowait())
            except queue.Empty:
                pass
            try:
                root.after(50, pump)
            except Exception:
                self._failed = True

        root.after(50, pump)
        try:
            root.mainloop()
        except Exception:
            self._failed = True


_WORKER = _BadgeWorker()


class UniActionBadge:
    """Lightweight facade over the process-lifetime badge worker."""

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
        self.enabled = bool(enabled)
        self.label = label
        self.duration_ms = max(100, int(duration_ms))
        self.offset_x = int(offset_x)
        self.offset_y = int(offset_y)
        self.ring_color = ring_color
        self._closed = False

    def _ensure_thread(self) -> bool:
        return not self._closed and self.enabled and _WORKER.ensure_started()
    def flash_at(self, x: int, y: int, action: str = "click") -> None:
        if not self._ensure_thread():
            return
        _WORKER.post({
            "x": int(x),
            "y": int(y),
            "action": str(action or "click"),
            "label": self.label,
            "duration_ms": self.duration_ms,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "ring_color": self.ring_color,
        })

    def close(self) -> None:
        """Close this facade without tearing down the process-lifetime Tcl worker."""
        self._closed = True
        self.enabled = False


_default_badge: Optional[UniActionBadge] = None


def get_default_badge() -> UniActionBadge:
    global _default_badge
    if _default_badge is None or _default_badge._closed:
        _default_badge = UniActionBadge()
    return _default_badge


def flash(x: int, y: int, action: str = "click") -> None:
    get_default_badge().flash_at(x, y, action)
