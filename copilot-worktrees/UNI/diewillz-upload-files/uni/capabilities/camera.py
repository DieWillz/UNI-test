from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

from uni.contracts import ToolResult
from .base import Capability


class CameraCapability(Capability):
    name = "camera"
    description = "Явно объявленный захват кадров с локальной веб-камеры"

    def __init__(
        self,
        artifact_dir: str | Path,
        *,
        device_index: int = 0,
        backend: str = "dshow",
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.device_index = device_index
        self.backend = backend.casefold()
        self.width = width
        self.height = height
        self._capture: Any = None
        self._lock = threading.Lock()

    def _backend_id(self) -> int:
        return {
            "dshow": cv2.CAP_DSHOW,
            "msmf": cv2.CAP_MSMF,
            "any": cv2.CAP_ANY,
        }.get(self.backend, cv2.CAP_DSHOW)

    def _start_sync(self) -> tuple[bool, str]:
        with self._lock:
            if self._capture is not None and self._capture.isOpened():
                return True, "Камера уже включена"
            capture = cv2.VideoCapture(self.device_index, self._backend_id())
            if not capture.isOpened():
                capture.release()
                return False, f"Не удалось открыть камеру с индексом {self.device_index}"
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
            frame_ok = False
            for _ in range(30):
                frame_ok, _ = capture.read()
                time.sleep(0.05)
            if not frame_ok:
                capture.release()
                return False, "Камера открылась, но не отдала кадр"
            self._capture = capture
            return True, "Камера включена после звукового уведомления"

    async def start(self, notice_ack: bool = False) -> ToolResult:
        if not notice_ack:
            return ToolResult(
                success=False,
                message="Камера не включена: сначала требуется звуковое уведомление",
            )
        try:
            success, message = await asyncio.to_thread(self._start_sync)
            return ToolResult(success=success, message=message)
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка включения камеры: {exc}")

    def _snapshot_sync(self, label: str) -> dict[str, Any]:
        with self._lock:
            if self._capture is None or not self._capture.isOpened():
                raise RuntimeError("Камера не включена")
            success, frame = self._capture.read()
            if not success:
                raise RuntimeError("Не удалось получить кадр")
            safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in label)[:60]
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            path = self.artifact_dir / f"{safe_label or 'camera'}_{timestamp}.jpg"
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError("Не удалось сохранить кадр")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return {
                "path": str(path.resolve()),
                "brightness": round(float(gray.mean()), 2),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            }

    async def snapshot(self, label: str = "camera") -> ToolResult:
        try:
            data = await asyncio.to_thread(self._snapshot_sync, label)
            return ToolResult(
                success=True,
                data=data,
                message="Кадр с камеры сохранён",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка кадра камеры: {exc}")

    def _stop_sync(self) -> bool:
        with self._lock:
            was_open = self._capture is not None
            if self._capture is not None:
                self._capture.release()
                self._capture = None
            return was_open

    async def stop(self) -> ToolResult:
        try:
            was_open = await asyncio.to_thread(self._stop_sync)
            return ToolResult(
                success=True,
                data={"was_open": was_open},
                message="Камера выключена" if was_open else "Камера уже была выключена",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка выключения камеры: {exc}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "start":
            return await self.start(bool(kwargs.get("notice_ack", False)))
        if action == "snapshot":
            return await self.snapshot(str(kwargs.get("label", "camera")))
        if action == "stop":
            return await self.stop()
        return ToolResult(success=False, message=f"Неизвестное действие camera.{action}")
