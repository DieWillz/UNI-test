"""Табличка-подпись курсора Uni: прозрачное always-on-top окно, следующее за мышью.

tkinter живёт в отдельном потоке и не блокирует asyncio-цикл агента.
Адаптировано из ТЗ «MVP xtoys browser mouse». Это ДОПОЛНЯЕТ существующий
uni.action_badge (который вспыхивает только на клике): здесь подпись
следует за курсором постоянно во время демо.

Импорт tkinter отложен внутри потока, чтобы модуль можно было импортировать
в headless-CI (где tkinter/дисплей могут отсутствовать) без падения.
"""

from __future__ import annotations

import queue
import sys
import threading
from dataclasses import dataclass

_MAGIC_COLOR = "#000001"  # цвет «выреза» для прозрачности на Windows


@dataclass(slots=True)
class CursorLabelConfig:
    text: str = "Uni"
    offset_x: int = 18
    offset_y: int = 24
    background: str = "#101828"
    foreground: str = "#F5F7FF"
    border: str = "#7C3AED"
    font_family: str = "Segoe UI"
    font_size: int = 11
    follow_ms: int = 16  # ~60 FPS следования


class CursorLabelOverlay:
    """Thread-safe подпись курсора: start() → show() → set_text() → stop()."""

    def __init__(self, config: CursorLabelConfig | None = None) -> None:
        self._config = config or CursorLabelConfig()
        self._commands: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._alive = threading.Event()

    # ---------- публичный API ----------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        _enable_dpi_awareness()
        self._alive.set()
        self._thread = threading.Thread(target=self._run, name="uni-cursor-label", daemon=True)
        self._thread.start()

    def show(self) -> None:
        self._post("show")

    def hide(self) -> None:
        self._post("hide")

    def set_text(self, text: str) -> None:
        self._post("text", text)

    def stop(self, timeout: float = 2.0) -> None:
        self._alive.clear()
        self._post("stop")
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    # ---------- внутреннее ----------
    def _post(self, command: str, payload: str | None = None) -> None:
        self._commands.put((command, payload))

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            # headless / нет tkinter — тихо не работаем (бейдж action_badge тоже так)
            return
        cfg = self._config
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=_MAGIC_COLOR)
        try:
            root.attributes("-transparentcolor", _MAGIC_COLOR)
        except tk.TclError:
            root.configure(bg=cfg.background)  # не Windows — просто фон

        label = tk.Label(
            root,
            text=cfg.text,
            bg=cfg.background,
            fg=cfg.foreground,
            font=(cfg.font_family, cfg.font_size, "bold"),
            padx=10,
            pady=4,
            highlightthickness=2,
            highlightbackground=cfg.border,
        )
        label.pack()
        root.geometry("+99999+99999")
        visible = False

        def tick() -> None:
            nonlocal visible
            while True:
                try:
                    command, payload = self._commands.get_nowait()
                except queue.Empty:
                    break
                if command == "show":
                    visible = True
                    root.attributes("-topmost", True)  # перезащитить topmost
                elif command == "hide":
                    visible = False
                elif command == "text" and payload is not None:
                    label.configure(text=payload)

            if not self._alive.is_set():
                root.destroy()
                return

            if visible:
                x, y = root.winfo_pointerxy()
                root.geometry(f"+{x + cfg.offset_x}+{y + cfg.offset_y}")
            else:
                root.geometry("+99999+99999")
            root.after(cfg.follow_ms, tick)

        root.after(cfg.follow_ms, tick)
        root.mainloop()


def _enable_dpi_awareness() -> None:
    """Чтобы координаты курсора и окна подписи совпадали на Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 — не критично
        pass
