"""Motion-to-Toy: преобразование движения на экране в интенсивность устройства.

Адаптировано из reference-реализации mov2toy.pyw (только алгоритм):
* выбор области экрана;
* захват через mss;
* grayscale + cv2.calcOpticalFlowFarneback;
* расчёт divergence / интенсивности;
* dead zone, gain, EMA-сглаживание, gamma-кривая, ограничение максимума.

НЕ перенесено: Tkinter GUI, Serial, TCP 12347, каналы L0/V0, hotkey,
прямая отправка команд устройству. Все команды идут через ToyControlCoordinator.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class MotionSettings:
    left: int = 0
    top: int = 0
    width: int = 640
    height: int = 480
    threshold: float = 2.6
    gain: float = 10.0
    smoothing: float = 0.95
    period_ms: int = 140
    max_intensity: float = 70.0
    gamma: float = 3.7


class MotionToyController:
    """Захватывает область экрана и шлёт интенсивность через координатор."""

    def __init__(self, coordinator: Any) -> None:
        self._coordinator = coordinator
        self._settings: Optional[MotionSettings] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop = getattr(coordinator, "_loop", None)
        self._last_value: float = 0.0
        self._error: Optional[str] = None
        self._region: dict = {}

    # ---- region selection ----
    def set_region(self, region: dict) -> None:
        self._region = {
            "left": int(region.get("left", 0)),
            "top": int(region.get("top", 0)),
            "width": int(region.get("width", 0)),
            "height": int(region.get("height", 0)),
        }

    # ---- lifecycle ----
    async def start(self, settings: MotionSettings) -> None:
        if self._running:
            return
        if not self._region or self._region.get("width", 0) <= 0 or self._region.get("height", 0) <= 0:
            raise ValueError("область не выбрана")
        self._settings = settings
        self._running = True
        self._error = None
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._running = False
        # При остановке — обязательно 0%.
        try:
            await self._coordinator.set_intensity("motion", 0.0)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def status(self) -> dict:
        return {
            "running": self._running,
            "region": self._region,
            "value": round(self._last_value, 2),
            "error": self._error,
        }

    # ---- capture loop ----
    def _post_value(self, value: float) -> None:
        """Отправляет значение в координатор из capture-потока (безопасно)."""
        self._last_value = value
        try:
            coro = self._coordinator.set_intensity("motion", value)
            if self._loop is not None and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(coro, self._loop)
            else:
                # Синхронный фолбэк (координатор сам thread-safe).
                asyncio.new_event_loop().run_until_complete(coro) if False else None
                # Координатор делает run_coroutine_threadsafe внутри _send,
                # поэтому можно вызвать напрямую из любого потока.
                self._coordinator._loop = getattr(self._coordinator._bridge, "_loop", None)
                asyncio.run_coroutine_threadsafe(coro, self._coordinator._loop)
        except Exception as exc:  # noqa: BLE001
            self._error = f"send: {exc}"

    def _capture_loop(self) -> None:
        import cv2
        import mss

        s = self._settings
        region = self._region
        monitor = {
            "left": region["left"],
            "top": region["top"],
            "width": region["width"],
            "height": region["height"],
        }
        prev_gray = None
        prev_out = 0.0
        try:
            with mss.mss() as sct:
                while self._running:
                    start = time.time()
                    img = np.array(sct.grab(monitor))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

                    if prev_gray is not None:
                        flow = cv2.calcOpticalFlowFarneback(
                            prev_gray, gray, None,
                            pyr_scale=0.5, levels=3, winsize=15,
                            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
                        )
                        # divergence
                        div = (
                            np.gradient(flow[..., 0], axis=0)
                            + np.gradient(flow[..., 1], axis=1)
                        )
                        y, x = np.unravel_index(np.argmax(np.abs(div)), div.shape)
                        motion_value = float(abs(div[y, x]))

                        # --- формула из mov2toy.pyw ---
                        mv = motion_value - s.threshold
                        if mv < 0.0:
                            mv = 0.0
                        raw = mv * s.gain
                        cap = min(99.99, max(0.0, float(s.max_intensity)))
                        value = max(0.0, min(cap, raw))
                        # gamma-кривая
                        if cap > 0.0 and abs(s.gamma - 1.0) > 1e-6:
                            n = value / cap
                            n = max(0.0, min(1.0, n))
                            value = (n ** s.gamma) * cap
                        # EMA
                        if s.smoothing > 0.0:
                            out = s.smoothing * value + (1.0 - s.smoothing) * prev_out
                        else:
                            out = value
                        prev_out = out

                        if not self._running:
                            break
                        self._post_value(out)
                        # если движение ниже порога — постепенно к нулю (уже учтено: mv=0 -> value=0)
                    else:
                        self._post_value(0.0)

                    prev_gray = gray
                    # период обновления
                    elapsed = time.time() - start
                    sleep_for = max(0.0, (s.period_ms / 1000.0) - elapsed)
                    if sleep_for > 0:
                        time.sleep(sleep_for)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            # Ошибка захвата — останавливаем машинку.
            try:
                self._post_value(0.0)
                asyncio.run_coroutine_threadsafe(
                    self._coordinator.stop("motion"), self._coordinator._loop
                )
            except Exception:
                pass
            self._running = False
