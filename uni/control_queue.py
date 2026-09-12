"""Единый серверный контур управления устройством (Dorch / Fredorch Rotary).

Один источник истины о состоянии сессии, одна очередь, один исполнитель,
один механизм принятия решений, одна очередь озвучки.

См. ТЗ владельца (раздел «ЕДИНЫЙ КОНТУР УПРАВЛЕНИЯ»):
* Юни/LLM выбирает намерение и допустимый план (структурированная операция);
* серверная очередь хранит принятые действия;
* исполнитель реализует их через координатор (ToyControlCoordinator -> Intiface);
* диспетчер речи обслуживает все сообщения Юни;
* UI отображает серверное состояние.

Безопасность (AGENTS.md + ТЗ §12):
* Единственный физический путь: ToyControlCoordinator -> IntifaceBridge.oscillate(0..100).
* Никакого xtoys.app / DOM / Playwright / браузера для управления устройством.
* Автономное движение требует autonomous.enabled AND autonomous_physical AND
  verified_physical. max_intensity = 65 сохраняется. verified_physical не
  выставляется автоматически. STOP не снимается автоматически.
* Инвариант COMMAND -> ACTION -> RESULT -> OBSERVATION -> VERIFIED соблюдается:
  ToolResult.success / HTTP 200 / истечение таймера НЕ означают физическое
  движение; статус остаётся not_verified без независимого наблюдения.
"""

from __future__ import annotations

import asyncio
import time
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ============================================================================
# 1. Единый серверный каталог паттернов
# ============================================================================
# Длительности — единственные для UI, модели и исполнителя.
# Источник правды: uni/webui/js/curves.js (фронтенд уже показывает
# chaos = 27 c, ramp = 59 c). Backend xtoys_patterns.DEFAULT_DURATION=20
# и отдельная _p_ramp больше НЕ являются источником длительностей.
#
# Каждая кривая — список (seconds, intensity 0..100). Естественная длительность
# паттерна = сумма seconds. Интенсивность в кривой — это относительная форма
# (масштаб кривой); предел мощности задаётся отдельно параметром intensity_percent
# (для паттернов) или абсолютно (для hold).

_PATTERN_CATALOG: dict[str, list[tuple[float, int]]] = {
    "ramp": [
        (8.0, 15), (6.0, 25), (5.0, 10), (10.0, 35),
        (6.0, 20), (4.0, 5), (12.0, 40), (8.0, 30),
    ],
    "climb": [
        (8.0, 30), (10.0, 45), (8.0, 55), (6.0, 35),
        (12.0, 65), (8.0, 50), (6.0, 70), (5.0, 40),
    ],
    "pulse": [
        (3.0, 55), (2.0, 15), (3.0, 70), (2.0, 20),
        (4.0, 80), (2.0, 25), (3.0, 65), (4.0, 10),
    ],
    "peak": [
        (6.0, 75), (5.0, 90), (4.0, 70), (7.0, 95),
        (5.0, 85), (8.0, 60), (6.0, 100), (10.0, 40),
    ],
    "cooldown": [
        (12.0, 25), (10.0, 15), (12.0, 10), (15.0, 5),
        (10.0, 20), (15.0, 0),
    ],
    "wave": [(10.0, 15), (8.0, 30), (6.0, 45), (5.0, 60), (5.0, 75), (6.0, 90), (8.0, 60), (10.0, 30), (12.0, 10), (15.0, 0)],
    "hold": [(1.0, 100)],  # форма-заглушка; реальная длительность из параметра
    "наказание": [(2.0, 80), (0.5, 0), (2.0, 90), (0.5, 0), (1.5, 100), (0.5, 0), (3.0, 70), (1.0, 0), (2.0, 95), (1.0, 0), (4.0, 60), (2.0, 0)],
    "соблазнение": [(6.0, 20), (4.0, 35), (5.0, 50), (3.0, 65), (4.0, 80), (2.0, 100), (8.0, 10), (10.0, 0)],
    "игра": [(3.0, 30), (2.0, 60), (1.5, 15), (4.0, 80), (2.0, 40), (3.0, 70), (1.0, 10), (5.0, 90), (2.0, 50), (2.0, 20), (3.0, 85), (6.0, 0)],
    "всплеск": [(1.0, 90), (0.5, 20), (1.0, 100), (0.5, 10), (1.0, 85), (0.5, 30), (1.0, 95), (0.5, 15), (2.0, 70), (3.0, 0)],
    "длинная_волна": [(10.0, 15), (8.0, 30), (6.0, 45), (5.0, 60), (5.0, 75), (6.0, 90), (8.0, 60), (10.0, 30), (12.0, 10), (15.0, 0)],
    "хаос": [
        (2.5, 45), (1.2, 80), (3.8, 20), (0.8, 95),
        (4.2, 55), (1.5, 70), (2.0, 10), (3.0, 100),
        (1.0, 40), (2.0, 85), (5.0, 30), (7.0, 0),
    ],
    "доминирование": [(4.0, 50), (3.0, 70), (2.0, 90), (1.0, 100), (6.0, 80), (4.0, 60), (3.0, 95), (2.0, 40), (8.0, 20), (10.0, 0)],
    "ласка": [(12.0, 10), (6.0, 25), (10.0, 15), (5.0, 30), (8.0, 20), (4.0, 35), (15.0, 5), (20.0, 0)],
    "tease": [(10.0, 20), (8.0, 40), (6.0, 60), (4.0, 80), (2.0, 95), (1.0, 100), (3.0, 30), (8.0, 10)],
    "edge": [(4.0, 60), (2.0, 70), (3.0, 50), (2.0, 80), (5.0, 65), (3.0, 75), (2.0, 40), (4.0, 85), (3.0, 55), (6.0, 20)],
    "surge": [(6.0, 30), (8.0, 50), (5.0, 70), (4.0, 85), (3.0, 95), (6.0, 80), (8.0, 60), (10.0, 40), (12.0, 20)],
    "stutter": [(1.5, 80), (0.5, 20), (1.0, 90), (0.5, 10), (2.0, 70), (0.5, 30), (1.0, 100), (0.5, 15), (1.5, 60), (0.5, 25)],
    "deep": [(8.0, 75), (6.0, 85), (5.0, 90), (10.0, 80), (7.0, 70), (12.0, 60), (8.0, 50), (15.0, 30)],
    "punish": [(2.0, 100), (1.0, 0), (1.5, 100), (1.0, 0), (2.0, 95), (1.5, 0), (1.0, 100), (2.0, 0), (3.0, 90), (2.0, 0)],
    "surrender": [(12.0, 15), (10.0, 30), (8.0, 50), (6.0, 70), (4.0, 85), (2.0, 100), (4.0, 80), (6.0, 60), (8.0, 40), (10.0, 20), (12.0, 0)],
    # chaos = 27 с (см. ТЗ: Chaos — 27 секунд)
    "chaos": [
        (3.0, 45), (1.5, 90), (4.0, 20), (2.0, 80),
        (5.0, 10), (1.0, 100), (3.0, 60), (2.5, 30),
        (4.0, 70), (1.0, 50),
    ],
    "rhythm": [(2.0, 70), (1.0, 30), (2.0, 80), (1.0, 20), (2.0, 90), (1.0, 40), (2.0, 75), (1.0, 25), (3.0, 60), (2.0, 15)],
    "climax": [(5.0, 40), (4.0, 60), (3.0, 80), (2.0, 95), (1.0, 100), (0.5, 100), (8.0, 0)],
    "slow_deep": [
        (10.0, 15), (8.0, 25), (6.0, 35), (10.0, 45),
        (8.0, 55), (6.0, 65), (10.0, 75), (2.0, 80),
        (5.0, 80), (1.0, 70), (5.0, 80), (1.0, 70),
        (5.0, 80), (1.0, 75), (5.0, 80), (8.0, 60),
        (6.0, 40), (8.0, 20), (8.0, 0),
    ],
    "pleasure_waves": [
        (8.0, 20), (5.0, 40), (4.0, 20), (6.0, 30), (5.0, 60), (4.0, 30),
        (6.0, 40), (5.0, 80), (4.0, 40), (5.0, 50), (5.0, 100), (4.0, 50),
        (8.0, 30), (10.0, 0),
    ],
    "long_torture": [
        (15.0, 50), (2.0, 90), (1.0, 50), (15.0, 50), (2.0, 95), (1.0, 50),
        (15.0, 50), (2.0, 100), (1.0, 50), (15.0, 50), (2.0, 90), (1.0, 50),
        (15.0, 50), (2.0, 95), (1.0, 50), (15.0, 50), (2.0, 100), (1.0, 50),
        (10.0, 30), (10.0, 0),
    ],
    "deep_rhythm": [
        (5.0, 30), (4.0, 40), (3.0, 50), (2.0, 60), (2.0, 70), (1.5, 80),
        (1.0, 90), (1.0, 100), (2.0, 80), (2.0, 60), (3.0, 40), (5.0, 40),
        (4.0, 50), (3.0, 60), (2.0, 70), (2.0, 80), (1.5, 90), (1.0, 100),
        (1.0, 100), (2.0, 80), (2.0, 60), (3.0, 40), (5.0, 50), (4.0, 60),
        (3.0, 70), (2.0, 80), (2.0, 90), (1.5, 100), (1.0, 100), (1.0, 100),
        (3.0, 80), (4.0, 50), (6.0, 20), (6.0, 0),
    ],
    "random_surprise": [
        (12.0, 15), (8.0, 45), (5.0, 30), (10.0, 70), (6.0, 50), (9.0, 85),
        (4.0, 60), (7.0, 95), (5.0, 75), (8.0, 40), (10.0, 80), (6.0, 55),
        (7.0, 90), (5.0, 65), (9.0, 100), (4.0, 80), (8.0, 50), (10.0, 20), (12.0, 0),
    ],
}

# Простые генераторы (без кривой в каталоге): форма задаётся функцией.
SIMPLE_GENERATORS = {"wave_sin", "hold_abs"}


def pattern_natural_duration(pattern_id: str) -> float:
    """Естественная длительность паттерна в секундах (сумма сегментов кривой)."""
    curve = _PATTERN_CATALOG.get(pattern_id)
    if curve is None:
        return 0.0
    return float(sum(max(0.1, s) for s, _ in curve))


def list_patterns() -> list[str]:
    return sorted(_PATTERN_CATALOG.keys())


# ============================================================================
# 2. Структура шага и очереди
# ============================================================================

@dataclass
class QueueStep:
    """Один принятый шаг управления устройством."""
    id: str
    kind: str  # "pattern" | "hold"
    pattern_id: str = ""          # для kind=pattern
    intensity_percent: int = 0    # предел мощности (паттерн) или абсолютная (hold)
    duration_seconds: float = 0.0
    # абсолютные сроки (монотонные часы), чтобы сетевые задержки не накапливались
    starts_at: float = 0.0
    ends_at: float = 0.0
    status: str = "pending"       # pending | running | done | cancelled
    # факт: принятая команда Intiface и независимое наблюдение
    last_command_value: Optional[int] = None
    command_sent: bool = False
    verified: bool = False
    verification_note: str = ""
    speech: str = ""
    execution_announced: bool = False
    failure_announced: bool = False


@dataclass
class QueueOperation:
    """Структурированная операция от модели/пользователя (контракт)."""
    operation: str  # append | replace_pending | replace_all | remove_pending | clear_pending | stop
    items: list[dict[str, Any]] = field(default_factory=list)
    idempotency_key: str = ""
    reason: str = ""


# Лимиты очереди (пункт 6)
MAX_STEPS = 24
MAX_HORIZON_SECONDS = 3600.0      # 1 час суммарный горизонт
MAX_SESSION_SECONDS = 5400.0       # 1.5 часа непрерывной сессии
_HORIZON_WARN = "превышен горизонт очереди (макс 1 ч)"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


class ControlQueue:
    """Единая серверная очередь управления устройством.

    Потокобезопасно (asyncio.Lock). Один исполнитель (runner) опрашивает
    очередь и шлёт команды через coordinator. Все пути (чат, автономная
    инициатива, ручной ползунок) идут сюда.
    """

    def __init__(
        self,
        coordinator: Any = None,
        max_intensity: int = 65,
        allowed: Callable[[], bool] = lambda: False,
    ) -> None:
        self._coordinator = coordinator
        self.max_intensity = int(max(0, min(100, max_intensity)))
        self._allowed = allowed
        self._lock = asyncio.Lock()
        self.steps: list[QueueStep] = []
        self.queue_revision = 0          # меняется при логических изменениях плана
        self.control_epoch = 0           # поколение отмены (STOP)
        self._idempotency: dict[str, Any] = {}  # key -> (operation_result, expires_at)
        self.active_source: Optional[str] = None
        self.mode = "stopped"            # stopped | manual | autonomous | error
        self.stopped = True
        self.last_error: str = ""
        self.mute = False
        self.session_started_at = 0.0
        self._on_change: Optional[Callable[[dict], None]] = None
        self._on_execution: Optional[Callable[[dict], None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._manual_timer_task: Optional[asyncio.Task] = None

    # ---- конфигурация ----
    def configure(self, coordinator: Any, allowed: Callable[[], bool], max_intensity: int) -> None:
        self._coordinator = coordinator
        self._allowed = allowed
        self.max_intensity = int(max(0, min(100, max_intensity)))

    def set_change_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_change = cb

    def set_execution_callback(self, cb: Callable[[dict], None]) -> None:
        self._on_execution = cb

    def _emit_execution(self, event: dict[str, Any]) -> None:
        if self._on_execution is not None:
            try:
                self._on_execution(event)
            except Exception:
                pass

    def _notify(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change(self.status())
            except Exception:
                pass

    # ---- безопасность ----
    def _may_move(self) -> bool:
        try:
            return bool(self._allowed()) and not self.stopped
        except Exception:
            return False

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    # ---- валидация одного шага (пункт 4, 5) ----
    def _validate_item(self, item: dict[str, Any]) -> QueueStep:
        """Проверяет схему и параметры. Бросает ValueError при невалидном."""
        if not isinstance(item, dict):
            raise ValueError("item должен быть объектом")
        kind = str(item.get("type", "")).strip().lower()
        if kind not in ("pattern", "hold"):
            raise ValueError(f"неизвестный type шага: {kind!r} (ожидается pattern|hold)")
        speech = " ".join(str(item.get("speech", "")).split())[:500]
        if kind == "pattern":
            pid = str(item.get("pattern_id", "")).strip().lower()
            if pid not in _PATTERN_CATALOG:
                # запрещён fallback «неизвестное -> hold»
                raise ValueError(f"неизвестный паттерн: {pid!r}")
            intensity = item.get("intensity_percent", None)
            if intensity is None:
                intensity = 70
            intensity = _clamp(int(round(float(intensity))), 0, 100)
            duration = item.get("duration_seconds", None)
            if duration is None:
                duration = pattern_natural_duration(pid)
            else:
                duration = float(duration)
                if duration <= 0:
                    raise ValueError("duration_seconds должен быть > 0")
                # явное масштабирование кривой во времени, не неоговорённые повторы
                nat = pattern_natural_duration(pid)
                if nat > 0 and abs(duration - nat) / nat > 0.5:
                    # допускаем масштаб, но фиксируем фактически принятую длительность
                    pass
            if intensity > self.max_intensity:
                raise ValueError(f"intensity_percent {intensity} > max_intensity {self.max_intensity}")
            return QueueStep(
                id=self._new_id("step"),
                kind="pattern",
                pattern_id=pid,
                intensity_percent=int(intensity),
                duration_seconds=_clamp(duration, 1.0, MAX_HORIZON_SECONDS),
                speech=speech,
            )
        else:  # hold — абсолютная команда
            intensity = item.get("intensity_percent", None)
            if intensity is None:
                raise ValueError("hold требует intensity_percent")
            intensity = _clamp(int(round(float(intensity))), 0, 100)
            duration = item.get("duration_seconds", None)
            if duration is None:
                raise ValueError("hold требует duration_seconds")
            duration = float(duration)
            if duration <= 0:
                raise ValueError("duration_seconds должен быть > 0")
            if intensity > self.max_intensity:
                raise ValueError(f"intensity_percent {intensity} > max_intensity {self.max_intensity}")
            return QueueStep(
                id=self._new_id("step"),
                kind="hold",
                intensity_percent=int(intensity),
                duration_seconds=_clamp(duration, 0.5, MAX_HORIZON_SECONDS),
                speech=speech,
            )

    def _horizon_ok(self, added_seconds: float) -> bool:
        total = sum(s.duration_seconds for s in self.steps if s.status in ("pending", "running"))
        return (total + added_seconds) <= MAX_HORIZON_SECONDS

    # ---- применение операции (пункт 6: атомарно) ----
    async def apply(self, op: QueueOperation) -> dict[str, Any]:
        """Применяет структурированную операцию. Возвращает фактически принятую очередь."""
        async with self._lock:
            # идемпотентность: тот же ключ -> прежний результат, не добавляя шаги
            if op.idempotency_key:
                cached = self._idempotency.get(op.idempotency_key)
                if cached is not None and cached[1] > time.time():
                    return cached[0]
            operation = str(op.operation).strip().lower()

            if operation == "stop":
                result = await self._do_stop()
                self._cache_idem(op.idempotency_key, result)
                return result

            if operation == "clear_pending":
                result = await self._do_clear_pending()
                self._cache_idem(op.idempotency_key, result)
                return result

            if operation == "remove_pending":
                return await self._do_remove_pending(op, [])

            # операции, меняющие план, требуют валидации ВСЕГО нового плана ДО применения
            try:
                validated = [self._validate_item(it) for it in (op.items or [])]
            except ValueError as exc:
                # невалидная замена не уничтожает действующую очередь
                return self._reject(op.idempotency_key, f"операция отклонена: {exc}")

            if operation == "append":
                added = sum(s.duration_seconds for s in validated)
                if len(self.steps) + len(validated) > MAX_STEPS:
                    return self._reject(op.idempotency_key, f"превышен лимит шагов (макс {MAX_STEPS})")
                if not self._horizon_ok(added):
                    return self._reject(op.idempotency_key, _HORIZON_WARN)
                self.steps.extend(validated)
                self.queue_revision += 1
                self._schedule()
                result = self._accepted("append", validated)
                self._cache_idem(op.idempotency_key, result)
                self._notify()
                return result

            if operation == "replace_pending":
                # заменить только будущие шаги, не прерывая текущий
                result = await self._do_replace_pending(validated, op.idempotency_key)
                return result

            if operation == "replace_all":
                # Replacement is validated against the replacement itself; the
                # plan being discarded must not consume the new horizon budget.
                if len(validated) > MAX_STEPS:
                    return self._reject(op.idempotency_key, f"превышен лимит шагов (макс {MAX_STEPS})")
                if sum(s.duration_seconds for s in validated) > MAX_HORIZON_SECONDS:
                    return self._reject(op.idempotency_key, _HORIZON_WARN)
                result = await self._do_replace_all(validated, op.idempotency_key)
                return result

            return self._reject(op.idempotency_key, f"неизвестная операция: {operation}")

    def _cache_idem(self, key: str, result: dict) -> None:
        if key:
            self._idempotency[key] = (result, time.time() + 300.0)

    def _reject(self, key: str, reason: str) -> dict[str, Any]:
        self.last_error = reason
        result = {
            "accepted": False,
            "error": reason,
            "queue_revision": self.queue_revision,
            "control_epoch": self.control_epoch,
            "steps": self._public_steps(),
        }
        if key:
            self._idempotency[key] = (result, time.time() + 300.0)
        self._notify()
        return result

    def _accepted(self, operation: str, new_steps: list[QueueStep]) -> dict[str, Any]:
        return {
            "accepted": True,
            "operation": operation,
            "queue_revision": self.queue_revision,
            "control_epoch": self.control_epoch,
            "added": [s.id for s in new_steps],
            "total_seconds": round(sum(s.duration_seconds for s in self.steps), 1),
            "steps": self._public_steps(),
            "mode": self.mode,
        }

    # ---- конкретные операции ----
    async def _do_stop(self) -> dict[str, Any]:
        # немедленный ноль, отмена всей очереди, аварийная защёлка
        self.control_epoch += 1
        self.stopped = True
        self.mode = "stopped"
        # отменяем старые задачи/callbacks: статус -> cancelled
        for s in self.steps:
            if s.status in ("pending", "running"):
                s.status = "cancelled"
        self.active_source = None
        self.last_error = ""
        self.queue_revision += 1
        # отправляем ноль через координатор (безопасно: zero bypasses limits)
        await self._send_zero()
        self._notify()
        return {
            "accepted": True,
            "operation": "stop",
            "queue_revision": self.queue_revision,
            "control_epoch": self.control_epoch,
            "steps": self._public_steps(),
            "mode": self.mode,
        }

    async def _do_clear_pending(self) -> dict[str, Any]:
        for s in self.steps:
            if s.status == "pending":
                s.status = "cancelled"
        self.queue_revision += 1
        result = self._accepted("clear_pending", [])
        self._notify()
        return result

    async def _do_replace_pending(self, validated: list[QueueStep], key: str) -> dict[str, Any]:
        # Будущие шаги заменяются полностью. В горизонт входят только остаток
        # текущего running-шага и новый pending-план, а не удаляемые pending.
        new_steps = [s for s in self.steps if s.status == "running"]
        new_steps.extend(validated)
        if len(new_steps) > MAX_STEPS:
            return self._reject(key, f"превышен лимит шагов (макс {MAX_STEPS})")
        now = time.monotonic()
        running_remaining = sum(max(0.0, s.ends_at - now) for s in self.steps if s.status == "running")
        if running_remaining + sum(s.duration_seconds for s in validated) > MAX_HORIZON_SECONDS:
            return self._reject(key, _HORIZON_WARN)
        self.steps = new_steps
        self.queue_revision += 1
        self._schedule()
        result = self._accepted("replace_pending", validated)
        self._cache_idem(key, result)
        self._notify()
        return result

    async def _do_replace_all(self, validated: list[QueueStep], key: str) -> dict[str, Any]:
        # отменяем старое исполнение, отправляем ноль, затем новый план
        for s in self.steps:
            if s.status in ("pending", "running"):
                s.status = "cancelled"
        await self._send_zero()
        self.steps = list(validated)
        self.stopped = False
        self.mode = "autonomous" if self._may_move() else self.mode
        self.queue_revision += 1
        self._schedule()
        result = self._accepted("replace_all", validated)
        self._cache_idem(key, result)
        self._notify()
        return result

    async def _do_remove_pending(self, op: QueueOperation, validated: list[QueueStep]) -> dict[str, Any]:
        # удалить конкретный будущий шаг по стабильному id
        target_id = str((op.items[0] if op.items else {}).get("step_id", "")).strip()
        if not target_id:
            return self._reject(op.idempotency_key, "remove_pending требует step_id")
        before = len(self.steps)
        self.steps = [s for s in self.steps if not (s.id == target_id and s.status == "pending")]
        if len(self.steps) == before:
            return self._reject(op.idempotency_key, f"step_id {target_id} не найден среди будущих")
        self.queue_revision += 1
        result = self._accepted("remove_pending", [])
        self._cache_idem(op.idempotency_key, result)
        self._notify()
        return result

    # ---- планирование (абсолютные сроки) ----
    def _schedule(self) -> None:
        """Пересчитывает абсолютные starts_at/ends_at по монотонным часам."""
        now = time.monotonic()
        cursor = now
        for s in self.steps:
            if s.status == "done" or s.status == "cancelled":
                continue
            if s.status == "running":
                # текущий уже идёт: не сдвигаем, считаем от остатка
                remaining = max(0.0, s.ends_at - now)
                cursor = max(cursor, now + remaining)
                continue
            s.starts_at = cursor
            s.ends_at = cursor + s.duration_seconds
            s.status = "pending"
            cursor = s.ends_at

    # ---- исполнение (вызывается единым runner-ом) ----
    async def _send_value(self, value: int) -> bool:
        """Отправка через координатор. Возвращает, дошла ли команда (не факт движения)."""
        if self._coordinator is None:
            return False
        try:
            ok = await self._coordinator.set_intensity("autonomous", value)
            return bool(ok)
        except Exception:
            return False

    async def _send_zero(self) -> None:
        if self._coordinator is None:
            return
        try:
            # control_epoch is a generation counter, not a permanent STOP latch.
            # Only the current stopped flag means an emergency zero is required.
            if self.stopped:
                await self._coordinator.emergency_stop()
            else:
                await self._coordinator.set_intensity("autonomous", 0)
        except Exception:
            pass

    async def run_once(self) -> None:
        """Один тик исполнителя. Берёт текущий шаг, гонит его кривую/hold."""
        execution_event: dict[str, Any] | None = None
        async with self._lock:
            now = time.monotonic()
            current = None
            for s in self.steps:
                if s.status == "running":
                    current = s
                    break
                if s.status == "pending" and now >= s.starts_at:
                    s.status = "running"
                    current = s
                    break
            if current is None:
                if self.mode == "autonomous" and not self.stopped:
                    await self._send_value(0)
                return
            if now >= current.ends_at:
                current.status = "done"
                current.verified = False
                current.verification_note = "таймер истёк; физическое движение не подтверждено"
                await self._send_value(0)
                self.queue_revision += 1
                self._schedule()
                self._notify()
                return
            value = self._value_at(current, now)
            sent = await self._send_value(value)
            current.last_command_value = value
            current.command_sent = sent
            if sent:
                self.last_error = ""
                if not current.execution_announced:
                    current.execution_announced = True
                    execution_event = {
                        "type": "step_applied",
                        "step_id": current.id,
                        "kind": current.kind,
                        "pattern_id": current.pattern_id,
                        "commanded_value": int(value),
                        "speech": current.speech,
                        "message": "Команда Intiface принята; физическая обратная связь отсутствует",
                    }
            else:
                self.last_error = "Intiface: команда не принята; физический результат не подтверждён"
                if not current.failure_announced:
                    current.failure_announced = True
                    execution_event = {
                        "type": "step_failed",
                        "step_id": current.id,
                        "kind": current.kind,
                        "pattern_id": current.pattern_id,
                        "commanded_value": int(value),
                        "speech": "",
                        "message": self.last_error,
                    }
        if execution_event is not None:
            self._emit_execution(execution_event)

    def _value_at(self, step: QueueStep, now: float) -> int:
        """Целевая интенсивность (0..100) для момента now внутри шага."""
        if step.kind == "hold":
            return _clamp(step.intensity_percent, 0, self.max_intensity)
        # pattern: масштабируем кривую во времени, предел = intensity_percent
        curve = _PATTERN_CATALOG.get(step.pattern_id)
        if not curve:
            return 0
        total = sum(max(0.1, s) for s, _ in curve) or 1.0
        elapsed = max(0.0, now - step.starts_at)
        scale = max(0.1, step.duration_seconds) / total
        pos = elapsed / scale  # позиция в кривой (секунды)
        # найти сегмент
        acc = 0.0
        last_v = 0
        for seg_s, seg_v in curve:
            if pos <= acc + seg_s:
                last_v = seg_v
                break
            acc += seg_s
            last_v = seg_v
        # предел мощности — intensity_percent; кривая задаёт форму (масштаб 0..100 -> 0..intensity)
        factor = max(0, min(100, step.intensity_percent)) / 100.0
        return _clamp(round(last_v * factor), 0, self.max_intensity)

    # ---- публичное состояние (для UI и модели — один источник) ----
    def _public_steps(self) -> list[dict[str, Any]]:
        out = []
        for s in self.steps:
            if s.status == "cancelled":
                continue
            out.append({
                "id": s.id,
                "kind": s.kind,
                "pattern_id": s.pattern_id,
                "intensity_percent": s.intensity_percent,
                "duration_seconds": round(s.duration_seconds, 1),
                "status": s.status,
                "starts_at": round(s.starts_at, 2),
                "ends_at": round(s.ends_at, 2),
                "command_sent": s.command_sent,
                "verified": s.verified,
                "speech": s.speech,
            })
        return out

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        current = next((s for s in self.steps if s.status == "running"), None)
        pending = [s for s in self.steps if s.status == "pending"]
        total_remaining = 0.0
        for s in self.steps:
            if s.status in ("running", "pending"):
                total_remaining += max(0.0, s.ends_at - now)
        return {
            "mode": self.mode,
            "stopped": self.stopped,
            "emergency_stop": bool(getattr(self._coordinator, "emergency_stopped", False)),
            "control_epoch": self.control_epoch,
            "queue_revision": self.queue_revision,
            "max_intensity": self.max_intensity,
            "mute": self.mute,
            "current_step": (
                {
                    "id": current.id,
                    "kind": current.kind,
                    "pattern_id": current.pattern_id,
                    "intensity_percent": current.intensity_percent,
                    "duration_seconds": round(current.duration_seconds, 1),
                    "remaining_seconds": round(max(0.0, current.ends_at - now), 1),
                    "command_sent": current.command_sent,
                    "verified": current.verified,
                    "speech": current.speech,
                }
                if current is not None
                else None
            ),
            "pending_steps": [
                {
                    "id": s.id,
                    "kind": s.kind,
                    "pattern_id": s.pattern_id,
                    "intensity_percent": s.intensity_percent,
                    "duration_seconds": round(s.duration_seconds, 1),
                    "remaining_seconds": round(max(0.0, s.ends_at - now), 1),
                    "speech": s.speech,
                }
                for s in pending
            ],
            "total_remaining_seconds": round(total_remaining, 1),
            "last_error": self.last_error,
            "steps": self._public_steps(),
        }

    # ---- ручной источник (пункт 8: владелец забирает управление) ----
    async def _finish_manual_hold(self, step_id: str, duration: float, epoch: int) -> None:
        try:
            await asyncio.sleep(max(0.0, float(duration)))
        except asyncio.CancelledError:
            return
        async with self._lock:
            if epoch != self.control_epoch or self.mode != "manual_timed":
                return
            step = next((x for x in self.steps if x.id == step_id and x.status == "running"), None)
            if step is None:
                return
            if self._coordinator is not None:
                try:
                    await self._coordinator.release("manual")
                except Exception:
                    try:
                        await self._coordinator.set_intensity("manual", 0)
                    except Exception:
                        pass
            step.status = "done"
            step.last_command_value = 0
            self.active_source = None
            self.stopped = True
            self.mode = "stopped"
            self.queue_revision += 1
            self._manual_timer_task = None
            self._notify()

    async def manual_hold(self, value: int, duration: float, *, speech: str = "") -> dict[str, Any]:
        """Apply an exact user-requested power for a bounded time, then return to zero."""
        value = int(value)
        duration = float(duration)
        if value < 0 or value > self.max_intensity:
            return self._reject("", f"intensity_percent {value} > max_intensity {self.max_intensity}")
        if not 0 < duration <= MAX_HORIZON_SECONDS:
            return self._reject("", "duration_seconds ?????? ???? > 0 ? ?? ?????? 1 ????")
        async with self._lock:
            if getattr(self._coordinator, "emergency_stopped", False):
                return self._reject("", "??????? ????????? STOP")
            if self._manual_timer_task is not None and not self._manual_timer_task.done():
                self._manual_timer_task.cancel()
            for item in self.steps:
                if item.status in ("pending", "running"):
                    item.status = "cancelled"
            ok = bool(self._coordinator and await self._coordinator.set_intensity("manual", value))
            if not ok:
                return self._reject("", "Intiface ?? ?????? ???????")
            now = time.monotonic()
            step = QueueStep(
                id=self._new_id("manual"), kind="hold", intensity_percent=value,
                duration_seconds=duration, starts_at=now, ends_at=now + duration,
                status="running", last_command_value=value, command_sent=True, speech=speech,
            )
            self.steps = [step]
            self.stopped = False
            self.mode = "manual_timed"
            self.active_source = "manual"
            self.last_error = ""
            self.queue_revision += 1
            epoch = self.control_epoch
            self._manual_timer_task = asyncio.create_task(self._finish_manual_hold(step.id, duration, epoch))
            result = self._accepted("manual_hold", [step])
            result["transport_acknowledged"] = True
            result["current_value"] = value
            self._notify()
            return result

    async def pause(self) -> dict[str, Any]:
        """Gracefully stop motion and cancel the plan without latching emergency STOP."""
        async with self._lock:
            if self._manual_timer_task is not None and not self._manual_timer_task.done():
                self._manual_timer_task.cancel()
            self._manual_timer_task = None
            for item in self.steps:
                if item.status in ("pending", "running"):
                    item.status = "cancelled"
            source = self.active_source or getattr(self._coordinator, "active_source", None)
            if self._coordinator is not None:
                try:
                    if hasattr(self._coordinator, "stop"):
                        await self._coordinator.stop()
                    elif source:
                        await self._coordinator.release(source)
                    else:
                        await self._coordinator.set_intensity("manual", 0)
                except Exception:
                    pass
            self.active_source = None
            self.stopped = True
            self.mode = "stopped"
            self.last_error = ""
            self.queue_revision += 1
            self._notify()
            return self.status()

    async def manual_override(self, value: int) -> dict[str, Any]:
        """Осознанное изменение ручного ползунка во время автономной очереди
        = передача управления владельцу: отменяем конфликтующий план."""
        async with self._lock:
            if self.mode == "autonomous":
                for s in self.steps:
                    if s.status in ("pending", "running"):
                        s.status = "cancelled"
                self.stopped = False
                self.mode = "manual"
                self.queue_revision += 1
                await self._send_zero()
            self.mode = "manual"
            self.active_source = "manual"
        # команда идёт напрямую через координатор (ручной = высший приоритет)
        if self._coordinator is not None:
            try:
                await self._coordinator.set_intensity("manual", _clamp(value, 0, self.max_intensity))
            except Exception:
                pass
        self._notify()
        return self.status()

    def reset_stop(self) -> dict[str, Any]:
        """Снятие STOP владельцем. Не восстанавливает прежний план, не двигает устройство."""
        self.stopped = False
        self.control_epoch += 1
        self.mode = "stopped"
        self.last_error = ""
        self._notify()
        return self.status()

    def set_mute(self, mute: bool) -> None:
        self.mute = bool(mute)
        self._notify()


# ============================================================================
# 3. Парсинг намерения из естественной речи (для чата/автономной инициативы)
# ============================================================================
# Модель НЕ должна искать regex в произвольном тексте (пункт 4). Но для
# обратной совместимости с обычным чатом (когда пользователь пишет просто
# словами) сервер может предложить структурированную операцию модели, а не
# парсить regex. Эта функция — ТОЛЬКО вспомогательная подсказка для
# формирования операции моделью; она не исполняет команды сама по себе.
_INTENSITY_RE = re.compile(r"(\d{1,3})\s*%")
_DURATION_RE = re.compile(r"(\d{1,3})\s*(?:сек|s|с)")
_PAT_RE = re.compile(r"\b(chaos|ramp|climb|pulse|wave|hold|cooldown|peak|edge|surge|tease|deep|punish|surrender|наказание|соблазнение|игра|всплеск|ласка|длинная_волна|доминирование|rhythm|climax|slow_deep|pleasure_waves|long_torture|deep_rhythm|random_surprise)\b", re.I)


def suggest_operation_from_text(text: str) -> Optional[QueueOperation]:
    """Подсказка: НЕ исполняет. Возвращает структурированную операцию, если
    текст явно похож на команду устройства. Иначе None (обычный диалог)."""
    t = (text or "").lower()
    if not any(w in t for w in ("машинк", "мощность", "интенсив", "крути", "chaos", "ramp", "hold", "%", "дорч", "устройств")):
        return None
    # hold абсолютный
    m_int = _INTENSITY_RE.search(t)
    m_dur = _DURATION_RE.search(t)
    m_pat = _PAT_RE.search(t)
    if m_pat and m_pat.group(1).lower() in _PATTERN_CATALOG:
        pid = m_pat.group(1).lower()
        intensity = int(m_int.group(1)) if m_int else 70
        duration = float(m_dur.group(1)) if m_dur else pattern_natural_duration(pid)
        return QueueOperation(
            operation="append",
            items=[{"type": "pattern", "pattern_id": pid,
                    "intensity_percent": intensity, "duration_seconds": duration}],
        )
    if m_int and m_dur:
        return QueueOperation(
            operation="append",
            items=[{"type": "hold", "intensity_percent": int(m_int.group(1)),
                    "duration_seconds": float(m_dur.group(1))}],
        )
    return None
