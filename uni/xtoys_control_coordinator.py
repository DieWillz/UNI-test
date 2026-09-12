"""DorchControlCoordinator — единый владелец управления устройством.

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
    uni_in_chat: str = "suggest"

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
        self._autonomous_allowed: Callable[[], bool] = lambda: False
        self._autonomous_session = False
        self.stop_generation = 0

    def configure_autonomous(self, allowed: Callable[[], bool]) -> None:
        """Live config + owner acknowledgement gate, supplied by the agent."""
        self._autonomous_allowed = allowed

    def autonomous_allowed(self) -> bool:
        try:
            return bool(self._autonomous_allowed()) and not self.emergency_stopped
        except Exception:
            return False

    def _autonomous_preemption(self, source: str, preempt: bool = False) -> bool:
        return (
            source == AUTONOMOUS and self.autonomous_allowed()
            and (preempt or self._autonomous_session)
            and self.active_source in {None, AUTONOMOUS, MANUAL, PATTERN, MOTION}
        )

    # ---- публичные настройки ----
    def set_change_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_change = cb

    def set_max_intensity(self, value: float) -> None:
        self.max_intensity = max(0.0, min(100.0, float(value)))

    # ---- низкоуровневая отправка в устройство ----
    async def _send(self, value: float) -> bool:
        """Send and wait for the Intiface result."""
        value = max(0.0, min(self.max_intensity, float(value)))
        if value > 0 and self.emergency_stopped:
            return False
        if value > 0 and self.active_source == AUTONOMOUS and not self.autonomous_allowed():
            return False
        if self._bridge is None:
            return False
        try:
            result = await self._bridge.oscillate(int(round(value)))
        except Exception:
            return False
        if not isinstance(result, dict) or not result.get("ok"):
            return False
        self.current_value = float(int(round(value)))
        self._last_send = time.time()
        return True

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change(self.status())
            except Exception:
                pass

    # ---- управление источниками ----
    async def acquire(self, source: str, *, preempt: bool = False) -> bool:
        async with self._lock:
            if self.emergency_stopped:
                return False
            if source == AUTONOMOUS and not self.autonomous_allowed():
                return False
            takeover = self._autonomous_preemption(source, preempt)
            if self.active_source == source:
                if takeover:
                    self._autonomous_session = True
                return True
            # Приоритет: новый источник не может вытеснить более приоритетный
            # (кроме ручного, который может забрать управление у любого).
            if self.active_source is not None:
                cur_prio = _SOURCE_PRIORITY.get(self.active_source, 99)
                new_prio = _SOURCE_PRIORITY.get(source, 99)
                if new_prio > cur_prio and source != MANUAL and not takeover:
                    return False
            # Переключение источника: сначала 0%.
            if self.active_source is not None and self.active_source != source:
                if not await self._send(0.0):
                    return False
            self.active_source = source
            if takeover:
                self._autonomous_session = True
            self._notify()
            return True

    async def release(self, source: str) -> None:
        async with self._lock:
            if source == AUTONOMOUS:
                self._autonomous_session = False
            if self.active_source == source:
                await self._send(0.0)
                self.active_source = None
                self._notify()

    async def set_intensity(self, source: str, value: float) -> bool:
        async with self._lock:
            # Emergency stop latches: nothing may move the device until the
            # owner explicitly resets it (safety requirement).
            if self.emergency_stopped:
                return False
            if source == AUTONOMOUS and value > 0 and not self.autonomous_allowed():
                if self.active_source == AUTONOMOUS:
                    await self._send(0.0)
                return False
            takeover = self._autonomous_preemption(source)
            # Только активный (или явно захватывающий) источник управляет.
            if self.active_source is not None and self.active_source != source:
                # Более приоритетный источник уже владеет — отказ.
                if _SOURCE_PRIORITY.get(self.active_source, 99) <= _SOURCE_PRIORITY.get(source, 99) and source != MANUAL and not takeover:
                    return False
            if self.active_source != source:
                # Автозахват (например, remote/motion сами не вызывали acquire).
                # Но соблюдаем правило приоритета: если уже есть владелец с
                # БОЛЬШИМ приоритетом (меньше число), не перехватываем.
                if self.active_source is not None:
                    cur_prio = _SOURCE_PRIORITY.get(self.active_source, 99)
                    new_prio = _SOURCE_PRIORITY.get(source, 99)
                    if new_prio > cur_prio and source != MANUAL and not takeover:
                        return False
                    if not await self._send(0.0):
                        return False
                self.active_source = source
            # Rate-limit: объединяем частые команды.
            now = time.time()
            if value > 0 and source not in {AUTONOMOUS, MANUAL} and now - self.last_command_at < _MIN_COMMAND_INTERVAL:
                # DEPRECATED by Codex: an unsent value must not appear as applied.
                # self.current_value = max(0.0, min(self.max_intensity, float(value)))
                # self.last_command_at = now
                # return True
                return False
            self.last_command_at = now
            if not await self._send(value):
                return False
            self._notify()
            return True

    async def stop(self, source: Optional[str] = None) -> None:
        async with self._lock:
            if source in {None, AUTONOMOUS}:
                self._autonomous_session = False
            if source is None or self.active_source == source:
                await self._send(0.0)
                self.active_source = None
                self._notify()

    async def emergency_stop(self) -> bool:
        # Latch before waiting for a command already in flight. Zero bypasses limits.
        self.emergency_stopped = True
        self.stop_generation += 1
        self._autonomous_session = False
        async with self._lock:
            # Latched: stays True until reset_emergency() is called by the owner.
            # No source may move the device while latched.
            self.emergency_stopped = True
            sent = await self._send(0.0)
            self.active_source = None
            self._notify()
            return sent

    def reset_emergency(self) -> None:
        """Owner-only unlatch. Caller must be the human owner (e.g. via the
        hardware stop button / admin panel). Does NOT auto-move the device."""
        self.emergency_stopped = False
        self._notify()

    # ---- удалённая сессия ----
    def create_remote_session(self, max_intensity: float, ttl: float = 1800.0, uni_in_chat: str = "suggest") -> RemoteSession:
        import secrets
        token = secrets.token_hex(16)  # 128 бит
        self.remote_session = RemoteSession(
            token=token,
            max_intensity=max(0.0, min(100.0, float(max_intensity))),
            created_at=time.time(),
            ttl=float(ttl),
            uni_in_chat=uni_in_chat if uni_in_chat in {"off", "suggest", "assist"} else "suggest",
        )
        return self.remote_session

    def end_remote_session(self) -> None:
        if self.remote_session is not None:
            was_active = self.active_source == REMOTE
            self.remote_session = None
            # Сессия завершилась — обязательно отправляем 0%, если remote был
            # активен (устройство не должно оставаться на последнем значении).
            if was_active:
                import asyncio
                loop = self._loop
                if loop is not None and not loop.is_closed():
                    asyncio.run_coroutine_threadsafe(self._send(0.0), loop)
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
                    "uni_in_chat": rs.uni_in_chat if rs else "off",
                }
                if rs is not None
                else None
            ),
        }
