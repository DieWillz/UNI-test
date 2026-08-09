"""Intiface (Buttplug) bridge — direct device control from Python.

This talks to an Intiface server over WebSocket using the *verified* ``buttplug``
package (the same path the user's working DeviceController uses). It intentionally
does NOT go through a raw browser WebSocket, because Intiface's server has a known
V3 bug that breaks hand-rolled JSON clients ("Message V2 ServerInfo ... not in Spec
V3"). The buttplug package negotiates the handshake correctly.

Usage:
    bridge = IntifaceBridge("ws://127.0.0.1:12345")
    await bridge.connect()
    await bridge.oscillate(60)        # 0..100 — drive the machine
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from buttplug import Client, ProtocolSpec, WebsocketConnector

logger = logging.getLogger("uni.intiface")


class IntifaceBridge:
    """Thin async wrapper around a Buttplug client connected to Intiface."""

    def __init__(self, url: str = "ws://127.0.0.1:12345") -> None:
        self.url = url
        self.client: Client | None = None
        self._task: asyncio.Task[None] | None = None
        self.connected = False
        self.last_error: str = ""

    async def connect(self) -> dict[str, Any]:
        if self.connected and self.client is not None:
            return {"ok": True, "already": True, "devices": self._device_names()}
        try:
            self.client = Client("UNI Panel", ProtocolSpec.v3)
            connector = WebsocketConnector(self.url)
            await self.client.connect(connector)
            # Start the client's message pump (keeps ping/events flowing).
            self._task = asyncio.create_task(self.client.run(), name="uni.intiface")
            # Give the server a moment to enumerate devices.
            await asyncio.sleep(1.0)
            self.connected = True
            self.last_error = ""
            return {"ok": True, "devices": self._device_names()}
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            logger.warning(f"Intiface connect failed: {exc}")
            return {"ok": False, "error": str(exc)}

    async def disconnect(self) -> dict[str, Any]:
        try:
            if self.client is not None:
                await self.client.disconnect()
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.client = None
        self.connected = False
        return {"ok": True, "connected": False}

    def _device_names(self) -> list[str]:
        if self.client is None or not hasattr(self.client, "devices"):
            return []
        try:
            return [getattr(d, "name", str(d)) for d in self.client.devices]
        except Exception:
            return []

    def _pick_device(self):
        if self.client is None or not hasattr(self.client, "devices"):
            return None
        devices = list(self.client.devices)
        return devices[0] if devices else None

    async def oscillate(self, value: int) -> dict[str, Any]:
        """Drive the machine: 0..100. Picks the first device and uses whatever
        actuation it supports (oscillate > rotate > vibrate)."""
        value = max(0, min(100, int(value)))
        if not self.connected or self.client is None:
            return {"ok": False, "error": "не подключено к Intiface"}
        device = self._pick_device()
        if device is None:
            return {"ok": False, "error": "устройство не найдено (Connect на Intiface)"}
        try:
            speed = value / 100.0
            sent = False
            # Try capabilities in order of preference for a "machine" feel.
            if getattr(device, "oscillate_cmd", None) is not None:
                await device.oscillate_cmd(speed)
                sent = True
            elif getattr(device, "rotate_cmd", None) is not None:
                await device.rotate_cmd(speed, clockwise=True)
                sent = True
            elif getattr(device, "vibrate_cmd", None) is not None:
                await device.vibrate_cmd(speed)
                sent = True
            if not sent:
                return {"ok": False, "error": "устройство не поддерживает oscillate/rotate/vibrate"}
            return {"ok": True, "value": value, "device": getattr(device, "name", "?")}
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            logger.warning(f"Intiface oscillate failed: {exc}")
            return {"ok": False, "error": str(exc)}

    async def stop(self) -> dict[str, Any]:
        if not self.connected or self.client is None:
            return {"ok": True, "note": "не подключено"}
        device = self._pick_device()
        if device is None:
            return {"ok": True, "note": "нет устройства"}
        try:
            if getattr(device, "stop", None) is not None:
                await device.stop()
            elif getattr(device, "vibrate_cmd", None) is not None:
                await device.vibrate_cmd(0.0)
            elif getattr(device, "rotate_cmd", None) is not None:
                await device.rotate_cmd(0.0, clockwise=True)
            elif getattr(device, "oscillate_cmd", None) is not None:
                await device.oscillate_cmd(0.0)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "url": self.url,
            "devices": self._device_names(),
            "last_error": self.last_error,
        }
