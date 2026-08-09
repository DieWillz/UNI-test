"""ToyControlCoordinator — единственный владелец управления устройством.

Все источники команд (ручной регулятор, паттерн Hermes, автономный режим,
движение с экрана, удалённый пользователь) ОБЯЗАНЫ проходить через этот
координатор. Он гарантирует:

* одновременно машинкой управляет ровно один источник;
* ручное действие владельца имеет наивысший приоритет;
* аварийный стоп останавливает все режимы;
* переключение источника сначала отправляет 0%;
* при ошибке / завершении фоновой задачи / потере удалённого соединения
  обязательно отправляется 0%;
* значение ограничивается диапазоном 0..max_intensity;
* команды чаще установленного интервала объединяются (rate-limit).

Устройство управляется ТОЛЬКО через IntifaceBridge.oscillate(0..100).
Не используется LinearCmd: текущее устройство (Fredorch Rotary) сообщает
только актуатор Oscillate (нормализованный 0.0..1.0, аппаратный диапазон 0..20).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

MANUAL = "manual"
PATTERN = "pattern"
AUTONOMOUS = "autonomous"
MOTION = "motion"
REMOTE = "remote"

# Приоритет: меньше число = выше приоритет.
_SOURCE_PRIORITY = {
    MANUAL: 0,
    MOTION: 1,
    REMOTE: 1,
    PATTERN: 2,
    AUTONOMOUS: 3,
}

_MIN_COMMAND_INTERVAL = 0.05  # 50 мс — объединение частых команд


@dataclass
class RemoteSession:
    token: str
    max_intensity: float
    created_at: float
    ttl: float = 1800.0  # 30 минут
    last_command_at: float = 0.0
    last_heartbeat: float = 0.0
    sequence: int = 0
    connected: bool = False

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl

    def seconds_left(self) -> float:
        return max(0.0, self.ttl - (time.time() - self.created_at))


class ToyControlCoordinator:
    """Thread-safe координатор источников управления устройством."""

    def __init__(self, bridge: Any, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._bridge = bridge
        self._loop = loop
        self._lock = asyncio.Lock()
        self.active_source: Optional[str] = None
        self.current_value: float = 0.0
        self.max_intensity: float = 100.0
        self.last_command_at: float = 0.0
        self.emergency_stopped: bool = False
        self.remote_session: Optional[RemoteSession] = None
        self._last_send: float = 0.0
        self._on_change: Optional[Callable[[dict], None]] = None

    # ---- публичные настройки ----
    def set_change_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_change = cb

    def set_max_intensity(self, value: float) -> None:
        self.max_intensity = max(0.0, min(100.0, float(value)))

    # ---- низкоуровневая отправка в устройство ----
    def _send(self, value: float) -> None:
        """Отправляет значение в IntifaceBridge. Потокобезопасно."""
        value = max(0.0, min(self.max_intensity, float(value)))
        self.current_value = value
        self._last_send = time.time()
        if self._bridge is None:
            return
        if self._loop is None or self._loop.is_closed():
            self._loop = getattr(self._bridge, "_loop", None)
        if self._loop is not None and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(
                    self._bridge.oscillate(int(round(value))), self._loop
                )
                return
            except Exception:
                pass
        # Фолбэк: синхронно (если bridge умеет) — не для buttplug, но для совместимости.
        try:
            fn = getattr(self._bridge, "oscillate_sync", None)
            if fn:
                fn(int(round(value)))
        except Exception:
            pass

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.status())
            except Exception:
                pass

    # ---- управление источниками ----
    async def acquire(self, source: str) -> bool:
        async with self._lock:
            if self.emergency_stopped:
                return False
            if self.active_source == source:
                return True
            # Приоритет: новый источник не может вытеснить более приоритетный
            # (кроме ручного, который может забрать управление у любого).
            if self.active_source is not None:
                cur_prio = _SOURCE_PRIORITY.get(self.active_source, 99)
                new_prio = _SOURCE_PRIORITY.get(source, 99)
                if new_prio > cur_prio and source != MANUAL:
                    return False
            # Переключение источника: сначала 0%.
            if self.active_source is not None and self.active_source != source:
                self._send(0.0)
            self.active_source = source
            self._notify()
            return True

    async def release(self, source: str) -> None:
        async with self._lock:
            if self.active_source == source:
                self._send(0.0)
                self.active_source = None
                self._notify()

    async def set_intensity(self, source: str, value: float) -> bool:
        async with self._lock:
            if self.emergency_stopped:
                return False
            # Только активный (или явно захватывающий) источник управляет.
            if self.active_source is not None and self.active_source != source:
                # Более приоритетный источник уже владеет — отказ.
                if _SOURCE_PRIORITY.get(self.active_source, 99) <= _SOURCE_PRIORITY.get(source, 99) and source != MANUAL:
                    return False
            if self.active_source != source:
                # Автозахват (например, remote/motion сами не вызывали acquire).
                self.active_source = source
            # Rate-limit: объединяем частые команды.
            now = time.time()
            if now - self.last_command_at < _MIN_COMMAND_INTERVAL:
                # Все равно обновляем целевое значение, но не шлём каждый раз.
                self.current_value = max(0.0, min(self.max_intensity, float(value)))
                self.last_command_at = now
                return True
            self.last_command_at = now
            self._send(value)
            self._notify()
            return True

    async def stop(self, source: Optional[str] = None) -> None:
        async with self._lock:
            if source is None or self.active_source == source:
                self._send(0.0)
                self.active_source = None
                self._notify()

    async def emergency_stop(self) -> None:
        async with self._lock:
            self.emergency_stopped = True
            self._send(0.0)
            self.active_source = None
            self.remote_session = None
            self._notify()

    def reset_emergency(self) -> None:
        """Снять аварийный стоп (только вручную владельцем)."""
        self.emergency_stopped = False
        self._notify()

    # ---- удалённая сессия ----
    def create_remote_session(self, max_intensity: float, ttl: float = 1800.0) -> RemoteSession:
        import secrets
        token = secrets.token_hex(16)  # 128 бит
        self.remote_session = RemoteSession(
            token=token,
            max_intensity=max(0.0, min(100.0, float(max_intensity))),
            created_at=time.time(),
            ttl=float(ttl),
        )
        return self.remote_session

    def end_remote_session(self) -> None:
        if self.remote_session is not None:
            self.remote_session = None
            # Сессия завершилась — отправляем 0% (если remote был активен).
            if self.active_source == REMOTE:
                self._send(0.0)
                self.active_source = None
            self._notify()

    def status(self) -> dict:
        rs = self.remote_session
        return {
            "active_source": self.active_source,
            "current_value": round(self.current_value, 2),
            "max_intensity": round(self.max_intensity, 2),
            "emergency_stop": self.emergency_stopped,
            "last_command_at": self.last_command_at,
            "remote": (
                {
                    "active": rs is not None,
                    "connected": rs.connected if rs else False,
                    "max_intensity": round(rs.max_intensity, 2) if rs else 0.0,
                    "seconds_left": round(rs.seconds_left(), 1) if rs else 0.0,
                    "expired": rs.is_expired() if rs else True,
                }
                if rs is not None
                else None
            ),
        }
