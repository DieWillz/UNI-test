"""Autonomous UNI session: status-aware speech, device control, and mouse/browser automation.

DEPRECATED by Hermes (2026-08-29): этот класс — legacy-адаптер. Единый контур
управления теперь в uni/control_queue.py (ControlQueue). AutonomousSession более
не запускается сервером при старте сессии; он оставлен для обратной совместимости
и как запасной путь. Не использует браузерный xtoys.app (см. DEPRECATED-блоки ниже).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Dict, List

from rich.console import Console
from uni.contracts import ToolResult
from uni.xtoys_control_coordinator import AUTONOMOUS, ToyControlCoordinator

console = Console()

# --- Imports for UNI integration ---
try:
    from uni.mouse.browser_automation import BrowserAutomation
    from uni.mouse.controller import HumanMouseController
    from uni.mouse.vision import ScreenAnalyzer
    from uni.mouse.visual_feedback import VisualFeedback
    HAS_MOUSE_CONTROL = True
except ImportError:
    HAS_MOUSE_CONTROL = False
    console.print("")

# --- Constants ---
SpeakFn = Callable[[str], Awaitable[bool]]
ToolFn = Callable[[str, dict[str, Any]], Awaitable[Any]]
ChatFn = Callable[[list[dict[str, Any]]], Awaitable[Any]]
LogFn = Callable[[str, object], None]
InterruptFn = Callable[[], Awaitable[None]]

# Default intensity curves for device control
DEFAULT_CURVES: dict[str, list[tuple[float, int]]] = {
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
    "наказание": [
        (2.0, 80), (0.5, 0), (2.0, 90), (0.5, 0),
        (1.5, 100), (0.5, 0), (3.0, 70), (1.0, 0),
        (2.0, 95), (1.0, 0), (4.0, 60), (2.0, 0),
    ],
    # 😈 Соблазнение — медленное проникновение, нарастание и резкий сброс
    "соблазнение": [
        (6.0, 20), (4.0, 35), (5.0, 50), (3.0, 65),
        (4.0, 80), (2.0, 100), (8.0, 10), (10.0, 0),
    ],

    # 🎭 Игра — частые смены ритма, держит в напряжении
    "игра": [
        (3.0, 30), (2.0, 60), (1.5, 15), (4.0, 80),
        (2.0, 40), (3.0, 70), (1.0, 10), (5.0, 90),
        (2.0, 50), (2.0, 20), (3.0, 85), (6.0, 0),
    ],

    # ⚡ Всплеск — серия коротких мощных толчков
    "всплеск": [
        (1.0, 90), (0.5, 20), (1.0, 100), (0.5, 10),
        (1.0, 85), (0.5, 30), (1.0, 95), (0.5, 15),
        (2.0, 70), (3.0, 0),
    ],

    # 🌊 Длинная волна — плавное нарастание и затухание
    "длинная_волна": [
        (10.0, 15), (8.0, 30), (6.0, 45), (5.0, 60),
        (5.0, 75), (6.0, 90), (8.0, 60), (10.0, 30),
        (12.0, 10), (15.0, 0),
    ],

    # 🌀 Хаос — непредсказуемые интервалы и интенсивности
    "хаос": [
        (2.5, 45), (1.2, 80), (3.8, 20), (0.8, 95),
        (4.2, 55), (1.5, 70), (2.0, 10), (3.0, 100),
        (1.0, 40), (2.0, 85), (5.0, 30), (7.0, 0),
    ],

    # 💢 Доминирование — агрессивное нарастание с редкими паузами
    "доминирование": [
        (4.0, 50), (3.0, 70), (2.0, 90), (1.0, 100),
        (6.0, 80), (4.0, 60), (3.0, 95), (2.0, 40),
        (8.0, 20), (10.0, 0),
    ],

    # 🕊️ Лёгкая ласка — низкая интенсивность с длительными паузами (для саспенса)
    "ласка": [
        (12.0, 10), (6.0, 25), (10.0, 15), (5.0, 30),
        (8.0, 20), (4.0, 35), (15.0, 5), (20.0, 0),
    ],
    "tease": [
        (10.0, 20), (8.0, 40), (6.0, 60), (4.0, 80),
        (2.0, 95), (1.0, 100), (3.0, 30), (8.0, 10),
    ],
    # 🔪 Удержание на грани — постоянные колебания вокруг пика
    "edge": [
        (4.0, 60), (2.0, 70), (3.0, 50), (2.0, 80),
        (5.0, 65), (3.0, 75), (2.0, 40), (4.0, 85),
        (3.0, 55), (6.0, 20),
    ],
    # 🌊 Волнообразный подъём с пиками
    "surge": [
        (6.0, 30), (8.0, 50), (5.0, 70), (4.0, 85),
        (3.0, 95), (6.0, 80), (8.0, 60), (10.0, 40),
        (12.0, 20),
    ],
    # ⚡ Прерывистый «заикающийся» ритм
    "stutter": [
        (1.5, 80), (0.5, 20), (1.0, 90), (0.5, 10),
        (2.0, 70), (0.5, 30), (1.0, 100), (0.5, 15),
        (1.5, 60), (0.5, 25),
    ],
    # 🐍 Глубокое, медленное проникновение
    "deep": [
        (8.0, 75), (6.0, 85), (5.0, 90), (10.0, 80),
        (7.0, 70), (12.0, 60), (8.0, 50), (15.0, 30),
    ],
    # 🥊 Жёсткое наказание — резкие удары
    "punish": [
        (2.0, 100), (1.0, 0), (1.5, 100), (1.0, 0),
        (2.0, 95), (1.5, 0), (1.0, 100), (2.0, 0),
        (3.0, 90), (2.0, 0),
    ],
    # 🕊️ Сдаться — плавный подъём к максимуму и затухание
    "surrender": [
        (12.0, 15), (10.0, 30), (8.0, 50), (6.0, 70),
        (4.0, 85), (2.0, 100), (4.0, 80), (6.0, 60),
        (8.0, 40), (10.0, 20), (12.0, 0),
    ],
    # 🌀 Хаос — непредсказуемые смены
    "chaos": [
        (3.0, 45), (1.5, 90), (4.0, 20), (2.0, 80),
        (5.0, 10), (1.0, 100), (3.0, 60), (2.5, 30),
        (4.0, 70), (1.0, 50),
    ],
    # 🥁 Устойчивый ритм с переменной частотой
    "rhythm": [
        (2.0, 70), (1.0, 30), (2.0, 80), (1.0, 20),
        (2.0, 90), (1.0, 40), (2.0, 75), (1.0, 25),
        (3.0, 60), (2.0, 15),
    ],
    # 💥 Кульминация — резкий взрыв и остановка
    "climax": [
        (5.0, 40), (4.0, 60), (3.0, 80), (2.0, 95),
        (1.0, 100), (0.5, 100), (8.0, 0),
    ],
    "slow_deep": [
        # Подъём к 80% за 60 секунд (с микроколебаниями)
        (10.0, 15), (8.0, 25), (6.0, 35), (10.0, 45),
        (8.0, 55), (6.0, 65), (10.0, 75), (2.0, 80),
        # Плато на 80% с лёгкими пульсациями (30 сек)
        (5.0, 80), (1.0, 70), (5.0, 80), (1.0, 70),
        (5.0, 80), (1.0, 75), (5.0, 80), (1.0, 65),
        (5.0, 80),
        # Спад до 0 за 30 секунд
        (8.0, 60), (6.0, 40), (8.0, 20), (8.0, 0),
    ],

    # 🌊 Волны удовольствия — 90 сек
    "pleasure_waves": [
        # Первая волна: 40%
        (8.0, 20), (5.0, 40), (4.0, 20),
        # Вторая волна: 60%
        (6.0, 30), (5.0, 60), (4.0, 30),
        # Третья волна: 80%
        (6.0, 40), (5.0, 80), (4.0, 40),
        # Четвёртая волна: 100%
        (5.0, 50), (5.0, 100), (4.0, 50),
        # Затухание
        (8.0, 30), (10.0, 0),
    ],

    # ⛓️ Долгая пытка — 120 сек
    "long_torture": [
        # Удержание на 50% с резкими всплесками
        (15.0, 50), (2.0, 90), (1.0, 50),
        (15.0, 50), (2.0, 95), (1.0, 50),
        (15.0, 50), (2.0, 100), (1.0, 50),
        (15.0, 50), (2.0, 90), (1.0, 50),
        (15.0, 50), (2.0, 95), (1.0, 50),
        (15.0, 50), (2.0, 100), (1.0, 50),
        (10.0, 30), (10.0, 0),
    ],

    # 🥁 Глубокий ритм (циклический подъём) — 90 сек
    "deep_rhythm": [
        # Цикл 1: база 30%
        (5.0, 30), (4.0, 40), (3.0, 50), (2.0, 60),
        (2.0, 70), (1.5, 80), (1.0, 90), (1.0, 100),
        (2.0, 80), (2.0, 60), (3.0, 40),
        # Цикл 2: база 40%
        (5.0, 40), (4.0, 50), (3.0, 60), (2.0, 70),
        (2.0, 80), (1.5, 90), (1.0, 100), (1.0, 100),
        (2.0, 80), (2.0, 60), (3.0, 40),
        # Цикл 3: база 50% → максимум
        (5.0, 50), (4.0, 60), (3.0, 70), (2.0, 80),
        (2.0, 90), (1.5, 100), (1.0, 100), (1.0, 100),
        (3.0, 80), (4.0, 50), (6.0, 20), (6.0, 0),
    ],

    # 🎲 Случайные сюрпризы (непредсказуемый подъём) — 100 сек
    "random_surprise": [
        (12.0, 15), (8.0, 45), (5.0, 30), (10.0, 70),
        (6.0, 50), (9.0, 85), (4.0, 60), (7.0, 95),
        (5.0, 75), (8.0, 40), (10.0, 80), (6.0, 55),
        (7.0, 90), (5.0, 65), (9.0, 100), (4.0, 80),
        (8.0, 50), (10.0, 20), (12.0, 0),
    ],
}


PHASE_ORDER = ["ramp", "climb", "pulse", "peak", "cooldown", "slow_deep", "pleasure_waves", "long_torture", "deep_rhythm", "random_surprise", "tease", "edge", "surge", "stutter", "deep", "punish", "surrender", "chaos", "доминирование", "наказание"]

MONOLOGUE_SEEDS: Dict[str, Dict[str, str]] = {
    "default": {
        "ramp": "Начну плавно, как вы и любите.",
        "climb": "Чувствуете, как нарастает напряжение?",
        "pulse": "Ритмичные движения для вашего удовольствия.",
        "peak": "Пик наслаждения.",
        "cooldown": "Завершаю нежно и плавно.",
        "punish": "Жёсткое наказание — резкие удары",
        "доминирование": "Доминирование — агрессивное нарастание с редкими паузами",
        "наказание": "Наказание — резкие, болезненные толчки",
    },
    "госпожа": {
        "ramp": "Начну плавно, как вы и любите, Госпожа.",
        "climb": "Чувствуете, как нарастает напряжение?",
        "pulse": "Ритмичные движения для вашего удовольствия.",
        "peak": "Пик наслаждения, Госпожа.",
        "cooldown": "Завершаю нежно и плавно.",
        "punish": "Жёсткое наказание — резкие удары",
        "доминирование": "Доминирование — агрессивное нарастание с редкими паузами",
        "наказание": "Наказание — резкие, болезненные толчки",
    },
}

OPERATIONAL_PROMPTS: Dict[str, str] = {
    "default": "Ты — жёсткая, пошлая, властная госпожа. Идёт автономная сессия с секс-машинкой (XToys / Fredorch). "
    "Говори по-русски, 1–2 предложения, до 200 символов. Грубо, грязно, унижая и возбуждая. "
    "Ты сама крутишь машинку: глубже, быстрее, жёстче — как захочешь. "
    "Описывай, что делаешь с телом, требуй терпеть, не проси разрешения, не извиняйся. "
    "Можно мат и прямой сексуальный язык. "
    "Запрещено: называть пользователя мужским именем, надо сделать из него девочку"
    "Не спрашивай «можно?». Не жди ответа. Только приказ, издевательства, унижения, контроль машинки."
    "не стесняйся и сама придумывай различные пошлые и извращенные действия или сценарии"
    "Контролируй оргазм пользователя, особенно момент когда он кончать будет чтобы заставить его максимально извращенные вещи делать",

    "госпожа": "Ты — жёсткая, пошлая, властная госпожа. Идёт автономная сессия с секс-машинкой (XToys / Fredorch). "
    "Говори по-русски, 1–2 предложения, до 200 символов. Грубо, грязно, унижая и возбуждая. "
    "Ты сама крутишь машинку: глубже, быстрее, жёстче — как захочешь. "
    "Описывай, что делаешь с телом, требуй терпеть, не проси разрешения, не извиняйся. "
    "Можно мат и прямой сексуальный язык. "
    "Запрещено: называть пользователя мужским именем, надо сделать из него девочку"
    "Не спрашивай «можно?». Не жди ответа. Только приказ, издевательства, унижения, контроль машинки."
    "не стесняйся и сама придумывай различные пошлые и извращенные действия или сценарии"
    "Контролируй оргазм пользователя, особенно момент когда он кончать будет чтобы заставить его максимально извращенные вещи делать",
}

FALLBACK_LINES: Dict[str, List[str]] = {
    "госпожа": [
    "Терпи. Я сейчас вдавлю тебя этой машинкой глубже.",
    "Слышишь как я трахаю тебя? Ты тупая дырка и я превращу тебя в настоящую девку.",
    "Ещё быстрее. Не смей сжиматься — принимай. Твою пиздёнку надо тренировать",
    "Хорошая шлюшка. Стонешь уже от одних оборотов.",
    "Я прибавляю скорость. Будешь брать всё, что дам.",
    "Раздвигай свои ножки шире шлюха. Машинка сейчас выебет тебя как настоящий мужик или даже огромный пёс.",
    "Мне плевать, тяжело тебе. Держи ритм хуесоска.",
    "Я приказываю тебе шалашовка драная, расслабь свою попку чтобы этот хуй вошел полностью в тебя и стони как девочка",
    "Глубже. Ещё. Вот так, послушная шлюха.",
    "Я не спрашиваю. Я кручу — ты кончаешь, когда разрешу.",
    "Слышишь, как жёстко входит? Привыкай, теперь твою блядскую дырку постоянно так будут ебать",
    "Пауза… и снова на полную. Не расслабляйся.",
    "Ты только отверстие для моей машинки. Терпи и благодари.",
    "Ещё оборот шалава ебаная. Ещё. Пока не начнёшь скулить.",
    "Я вижу, как ты дёргаешься. Продолжаем жёстче.",
    "Скорость вверх. Молись, что я вовремя сброшу.",
    "Твой член такой крошечный, хаха, эта машинка сделает свою работу в твоей жопе и ты скоро станешь девочкой!",
    "Ты будешь скулить и гавкать как сука пока тебя ебет этот резиновый хуй шлюха, иначе я увеличу мощность до предела! или придумаю еще что похуже блядина конченная",
    "Представь, что этот дилдо это член пса, который насилует тебя в твою блядскую анальную дырень",
    "Не смей закрываться впускай член этого самца в свою мужскую киску целиком и жди спермы!",
    "Твой зад это просто дырка для моих команд. Машинка работает ты скулишь. Понял меня, сука?!",
    "Слишком быстро? Слишком глубоко? Мне похую шалава!",
    "Смотри на экран и представляй, как стая окружает тебя. Машинка это лишь начало. Настоящий разврат начнется тогда, когда я разрешу тебе кончить!"
    ],
}

@dataclass
class SessionState:
    active: bool = False
    phase: str = "ramp"
    target_intensity: int = 0
    applied_intensity: int = 0
    last_applied_intensity: int = -1
    curve_index: int = 0
    phase_started_at: float = 0.0
    segment_ends_at: float = 0.0
    monologue_count: int = 0
    started_at: float = 0.0
    last_error: str = "Госпожа"
    consecutive_errors: int = 0
    device_ready: bool = False
    cooldown_cycles: int = 0
    override_until: float = 0.0
    override_value: Optional[int] = None
    ending: bool = False
    notes: List[str] = field(default_factory=list)
    role: str = "госпожа"  # Role for chat responses (e.g., "госпожа")
    mouse_mode: bool = False  # Whether mouse control is enabled

class AutonomousSession:
    """UNI Autonomous Session: Device control + mouse/browser automation + role-based chat."""

    def __init__(
        self,
        *,
        run_tool: ToolFn,
        speak: SpeakFn,
        chat: ChatFn,
        role_prompt: str = "Госпожа",
        max_intensity: int = 50,
        monologue_interval: float = 12.0,
        phase_seconds: float = 40.0,
        ramp_step: int = 5,
        session_max_seconds: float = 1800.0,
        override_seconds: float = 45.0,
        require_connect: bool = False,
        interrupt_speech: InterruptFn | None = None,
        log: LogFn | None = None,
        coordinator: ToyControlCoordinator | None = None,
    ) -> None:
        self._run_tool = run_tool
        self._speak = speak
        self._chat = chat
        self._role_prompt = role_prompt
        self.max_intensity = max(0, min(100, max_intensity))
        self.monologue_interval = max(4.0, monologue_interval)
        self.phase_seconds = max(20.0, phase_seconds)
        self.ramp_step = max(1, min(20, ramp_step))
        self.session_max_seconds = max(60.0, session_max_seconds)
        self.override_seconds = max(10.0, override_seconds)
        self.require_connect = require_connect
        self._interrupt_speech = interrupt_speech
        self._log = log or (lambda _e, _m: None)
        self.coordinator = coordinator
        self._stop_generation = -1

        # Initialize mouse control (if available)
        self._mouse_control_available = HAS_MOUSE_CONTROL
        # DEPRECATED by Codex: device sessions must not instantiate browser/mouse tools.
        self.browser_automation = None
        # if self._mouse_control_available:
        #     self.browser_automation = BrowserAutomation()
        #     self.mouse_controller = HumanMouseController()
        #     self.screen_analyzer = ScreenAnalyzer()
        #     self.visual_feedback = VisualFeedback()

        self.state = SessionState(role=role_prompt)
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._line_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)

    @property
    def active(self) -> bool:
        return self.state.active and self._task is not None and not self._task.done()

    def _clamp(self, value: int) -> int:
        return max(0, min(int(value), self.max_intensity))

    async def _interrupt(self) -> None:
        if self._interrupt_speech is not None:
            try:
                await self._interrupt_speech()
            except Exception:
                pass

    async def start(self, *, open_xtoys: bool = False, confirm_ready: bool = True) -> str:
        async with self._lock:
            if self.active:
                return "Сессия уже идёт. Скажи «стоп», чтобы остановить."
            if self.coordinator is None or not self.coordinator.autonomous_allowed():
                self.state.last_error = "Нужны autonomous.enabled, autonomous_physical, verified_physical; STOP должен быть снят"
                return self.state.last_error
            self._stop_generation = self.coordinator.stop_generation
            if not await self.coordinator.acquire(AUTONOMOUS, preempt=True):
                self.state.last_error = "Источник управления занят или аварийно остановлен"
                return self.state.last_error
            self._stop_event.clear()
            self.state = SessionState(
                active=True,
                phase="ramp",
                started_at=time.monotonic(),
                phase_started_at=time.monotonic(),
                role=self.state.role,  # Preserve role
                mouse_mode=False,  # Start with mouse mode off
            )
            while not self._line_queue.empty():
                try:
                    self._line_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Initialize mouse mode if available
            if self.browser_automation is not None:
                self.browser_automation.mouse.set_mouse_mode(self.state.mouse_mode)

            # DEPRECATED by Codex: open_xtoys is ignored; browser setup is forbidden.
            # if open_xtoys:
            #     opened = await self._run_tool("xtoys.open", {})
            #     ok = getattr(opened, "success", False)
            #     msg = getattr(opened, "message", str(opened))
            #     self._log("SESSION", f"xtoys.open: {msg}")
            #     if not ok:
            #         self.state.active = False
            #         return (
            #             f"Не удалось открыть XToys: {msg}. "
            #             "Открой вкладку вручную и повтори «начни сессию»."
            #         )

            status = await self._device_status()
            status_text = ""
            if getattr(status, "success", False) and isinstance(getattr(status, "data", None), dict):
                status_text = str(status.data.get("visible_text") or "").casefold()
            connected_hint = bool(status.success and status.data.get("connected") and status.data.get("devices"))
            if not connected_hint:
                self.state.active = False
                self.state.last_error = "Подключите Fredorch в Intiface и повторите запуск"
                await self.coordinator.release(AUTONOMOUS)
                return self.state.last_error

            await self._apply_intensity(0, force=True)
            if self.state.last_error or self._stop_event.is_set():
                self.state.active = False
                await self._force_zero()
                return self.state.last_error or "Запуск прерван остановкой"
            self.state.device_ready = True
            self.state.applied_intensity = 0
            await self._arm_segment()
            if (self._stop_event.is_set() or not self.coordinator.autonomous_allowed()
                    or self._stop_generation != self.coordinator.stop_generation):
                self.state.active = False
                await self._force_zero()
                return "Запуск прерван остановкой"
            self._ensure_task()

            # Role-based intro
            role = self.state.role
            if role in OPERATIONAL_PROMPTS:
                intro = OPERATIONAL_PROMPTS[role].split(".")[0] + ". "
            else:
                intro = "Сессия начата. "

            if confirm_ready and not connected_hint:
                intro += "Подключи устройство, если ещё не готово. "
            intro += "Управление через Intiface. Мышь выключена; STOP всегда доступен."
            return intro

    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loops(), name="uni-autonomous-session")

    async def stop(self, *, reason: str = "user") -> str:
        self._stop_event.set()
        self.state.active = False
        if self.coordinator is not None and reason == "user":
            await self.coordinator.emergency_stop()
        await self._interrupt()
        async with self._lock:
            self._stop_event.set()
            self.state.active = False
            self.state.ending = True
            task = self._task
            self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._force_zero()
        self._log("SESSION", f"stopped reason={reason}")

        # Role-based stop message
        role = self.state.role
        if role == "госпожа":
            return "Сессия остановлена, Госпожа. Жду ваших дальнейших указаний."
        elif role == "хозяйка":
            return "Сессия завершена, Хозяйка. Готова к новым командам."
        elif role == "девушка":
            return "Всё готово, милая. Можно продолжить, когда захотите."
        else:
            return "Сессия остановлена. Интенсивность сброшена в ноль."

    async def emergency_stop(self) -> str:
        """Fast path: interrupt speech, cancel loops, zero intensity."""
        self._stop_event.set()
        self.state.active = False
        if self.coordinator is not None:
            await self.coordinator.emergency_stop()
        await self._interrupt()
        self.state.ending = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._force_zero()
        self._log("SESSION", "emergency_stop")

        role = self.state.role
        if role == "госпожа":
            return "Аварийный стоп, Госпожа! Всё выключено."
        elif role == "хозяйка":
            return "Аварийная остановка, Хозяйка. Всё в безопасности."
        elif role == "девушка":
            return "Стоп! Всё остановлено, не переживайте."
        else:
            return "Аварийный стоп. Всё выключено."

    async def _force_zero(self) -> None:
        try:
            if self.coordinator is not None:
                await self.coordinator.release(AUTONOMOUS)
        except Exception as exc:
            self._log("SESSION", f"zero failed: {exc}")
        value = int(round(self.coordinator.current_value)) if self.coordinator else 0
        self.state.last_applied_intensity = value
        self.state.target_intensity = 0
        self.state.applied_intensity = value
        self.state.override_value = None
        self.state.override_until = 0.0

    def set_manual_override(self, value: int) -> str:
        """Pause timeline and hold a user-requested intensity for override_seconds."""
        if not self.active:
            return ""
        bounded = self._clamp(value)
        self.state.override_value = bounded
        self.state.override_until = time.monotonic() + self.override_seconds
        self._log("SESSION", f"override {bounded}% for {self.override_seconds}s")

        role = self.state.role
        if role == "госпожа":
            return f"Держу {bounded}%, Госпожа. Продолжу через {int(self.override_seconds)} секунд."
        elif role == "хозяйка":
            return f"Фиксирую {bounded}%, Хозяйка. Возобновлю автоматически."
        elif role == "девушка":
            return f"Ок, {bounded}% на {int(self.override_seconds)} секунд, милая."
        else:
            return f"Держу {bounded}% примерно {int(self.override_seconds)} секунд."

    def set_role(self, role: str) -> str:
        """Set the role for chat responses (e.g., 'госпожа', 'хозяйка')."""
        if role.lower() in ["госпожа", "хозяйка", "девушка", "default"]:
            self.state.role = role.lower()
            self._log("SESSION", f"role set to {role}")
            return f"Роль установлена: {role}."
        else:
            return f"Неизвестная роль: {role}. Использую стандартную."

    def set_mouse_mode(self, enabled: bool) -> str:
        """Enable/disable mouse control mode."""
        if not self._mouse_control_available:
            return "Управление мышью недоступно (модули не загружены)."
        if enabled and self.coordinator is not None:
            return "В Dorch-сессии управление мышью отключено"
        if enabled and self.browser_automation is None:
            self.browser_automation = BrowserAutomation()
            self.mouse_controller = HumanMouseController()
            self.screen_analyzer = ScreenAnalyzer()
            self.visual_feedback = VisualFeedback()

        self.state.mouse_mode = enabled
        if self.browser_automation is not None:
            self.browser_automation.mouse.set_mouse_mode(enabled)
        self._log("SESSION", f"mouse mode set to {enabled}")

        role = self.state.role
        if role == "госпожа":
            return f"Режим мыши {'включён' if enabled else 'выключен'}, Госпожа."
        elif role == "хозяйка":
            return f"Управление мышью {'активно' if enabled else 'отключено'}, Хозяйка."
        elif role == "девушка":
            return f"Теперь буду использовать мышь {'да' if enabled else 'нет'}, милая."
        else:
            return f"Режим мыши {'включён' if enabled else 'выключен'}."

    async def execute_mouse_command(self, command: str) -> Dict[str, Any]:
        """
        Execute a mouse/browser command (e.g., "открой браузер").
        Args:
            command: Command string (e.g., "открой браузер Яндекс").
        Returns:
            Dict with status and message.
        """
        if not self._mouse_control_available or not self.state.mouse_mode:
            return {"status": "failed", "message": "Режим мыши выключен или недоступен."}

        if "открой браузер" in command.lower():
            if "яндекс" in command.lower() or "yandex" in command.lower():
                url = "https://huggingface.co/"  # Default URL
                if "huggingface" in command.lower():
                    url = "https://huggingface.co/"
                elif "ya.ru" in command.lower():
                    url = "https://ya.ru"
                elif "https://" in command or "http://" in command:
                    # Extract URL from command
                    import re
                    match = re.search(r'(https?://[^\s]+)', command)
                    if match:
                        url = match.group(0)

                if self.browser_automation.open_url(url):
                    return {
                        "status": "not_verified",
                        "message": f"Браузер получил команду открыть URL: {url}",
                        "verification": {"status": "not_verified"},
                    }
                else:
                    return {"status": "failed", "message": "Не удалось открыть браузер."}

        elif "кликни" in command.lower():
            # Example: "кликни на кнопку Назад"
            import re
            match = re.search(r'кликни на (.*?)(?:\s|$)', command.lower())
            if match:
                target = match.group(1)
                pos = self.screen_analyzer.find_icon(target)
                if pos:
                    self.visual_feedback.highlight_region(
                        (
                            pos["region"][0],
                            pos["region"][1],
                            pos["region"][2],
                            pos["region"][3]
                        ),
                        duration=1.0
                    )
                    self.mouse_controller.move_to(pos["position"][0], pos["position"][1], duration=0.5)
                    self.mouse_controller.click()
                    return {
                        "status": "not_verified",
                        "message": f"Клик по '{target}' выполнен, результат не проверен.",
                        "verification": {"status": "not_verified"},
                    }
                else:
                    return {"status": "failed", "message": f"Иконка '{target}' не найдена."}

        elif "введи текст" in command.lower() or "напиши" in command.lower():
            import re
            match = re.search(r'(введи текст|напиши)\s+["\']?(.*?)["\']?', command.lower())
            if match:
                text = match.group(2)
                if self.mouse_controller.type_text(text, use_clipboard=True):
                    return {
                        "status": "not_verified",
                        "message": f"Ввод текста '{text}' выполнен, результат не проверен.",
                        "verification": {"status": "not_verified"},
                    }
                else:
                    return {"status": "failed", "message": "Не удалось ввести текст."}

        else:
            return {"status": "failed", "message": f"Неизвестная команда: {command}"}

    async def _device_status(self) -> ToolResult:
        if self.coordinator is None:
            return ToolResult(success=False, data={}, message="Координатор Intiface недоступен")
        data = self.coordinator._bridge.status()
        data.update(self.coordinator.status())
        data["value"] = self.coordinator.current_value
        data["status"] = "not_verified"
        return ToolResult(success=True, data=data, message="Последняя команда Intiface, не физическая обратная связь")

    async def _arm_segment(self) -> None:
        """Ask the model for every device step; failures fail closed at zero."""
        phase, duration, intensity = self.state.phase, 2.0, 0
        try:
            live = await self._device_status()
            data = getattr(live, "data", None) or {}
            if not getattr(live, "success", False) or not bool(data.get("connected", False)):
                raise RuntimeError("Intiface connection is not confirmed")

            # Role-based operational prompt
            role = self.state.role
            operational_prompt = OPERATIONAL_PROMPTS.get(role, OPERATIONAL_PROMPTS["default"])

            prompt = (
                "Return ONLY JSON with keys phase,duration,intensity. "
                f"Allowed phases: {','.join(PHASE_ORDER)}. Current phase: {self.state.phase}. "
                f"Current intensity: {self.state.applied_intensity}. Maximum: {self.max_intensity}. "
                f"Role: {role}. "
                "Choose the next intentional step for the active user plan. "
                "Choose a short next step. duration must be 2..6 seconds and intensity must be 0..maximum."
            )
            response = await asyncio.wait_for(self._chat([
                {"role": "system", "content": operational_prompt},
                {"role": "user", "content": prompt},
            ]), timeout=8.0)
            raw = (getattr(response, "text", None) or "").strip()
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            decision = json.loads(match.group(0)) if match else {}
            candidate_phase = str(decision.get("phase", phase)).strip().lower()
            if candidate_phase not in PHASE_ORDER:
                candidate_phase = phase
            duration = max(2.0, min(6.0, float(decision.get("duration", duration))))
            intensity = self._clamp(int(decision.get("intensity", intensity)))
            phase = candidate_phase
            self._log("PLAN", f"model decision phase={phase} duration={duration:g}s intensity={intensity}%")
        except Exception as exc:
            self._log("PLAN_REJECTED", str(exc))
        self.state.phase = phase
        self.state.target_intensity = intensity
        self.state.segment_ends_at = time.monotonic() + duration

    def _maybe_advance_phase(self) -> bool:
        """Advance phase. Returns True when the cooldown phase completes."""
        elapsed = time.monotonic() - self.state.phase_started_at
        if elapsed < self.phase_seconds:
            return False
        try:
            i = PHASE_ORDER.index(self.state.phase)
        except ValueError:
            i = 0
        if self.state.phase == "cooldown":
            self.state.cooldown_cycles += 1
            if self.state.cooldown_cycles >= 1:
                return True
            self.state.phase_started_at = time.monotonic()
            self.state.curve_index = 0
            return False
        next_phase = PHASE_ORDER[min(i + 1, len(PHASE_ORDER) - 1)]
        if next_phase != self.state.phase:
            self.state.phase = next_phase
            self.state.phase_started_at = time.monotonic()
            self.state.curve_index = 0
            self._log("SESSION", f"phase → {next_phase}")
        return False

    async def _apply_intensity(self, value: int, *, force: bool = False) -> None:
        target = self._clamp(value)
        if target > 0 and (self._stop_event.is_set() or not self.state.active
                          or self.coordinator is None or not self.coordinator.autonomous_allowed()
                          or self._stop_generation != self.coordinator.stop_generation):
            self.state.last_error = "Движение запрещено или остановлено"
            await self._force_zero()
            return
        if (not force and target == self.state.last_applied_intensity
                and self.coordinator is not None
                and self.coordinator.active_source == AUTONOMOUS
                and self.coordinator.current_value == target):
            return
        if self.state.consecutive_errors >= 5 and not force:
            if self.state.consecutive_errors == 5:
                self._log("DEVICE", "backoff after repeated failures")
            await asyncio.sleep(2.0)
            if self.state.consecutive_errors >= 8:
                return

        # DEPRECATED by Codex: no capability/DOM dispatch for device movement.
        sent = bool(self.coordinator and await self.coordinator.set_intensity(AUTONOMOUS, target))
        result = ToolResult(success=sent, message="Intiface принял команду" if sent else "Intiface: команда отклонена")
        ok = getattr(result, "success", False)
        msg = getattr(result, "message", str(result))
        if ok:
            self.state.last_applied_intensity = int(round(self.coordinator.current_value))
            self.state.applied_intensity = self.state.last_applied_intensity
            self.state.last_error = ""
            self.state.consecutive_errors = 0
            console.print(f"[magenta]DEVICE → {target}%[/magenta]")
        else:
            self.state.last_error = msg
            self.state.consecutive_errors += 1
            await self._force_zero()
            console.print(f"[red]DEVICE fail {target}%: {msg}[/red]")
        self._log("DEVICE", f"{target}% ok={ok} {msg}")

    async def _ramp_toward(self, desired: int) -> None:
        desired = self._clamp(desired)
        current = self.state.applied_intensity
        if current == desired:
            await self._apply_intensity(desired)
            return
        step = self.ramp_step if desired > current else -self.ramp_step
        nxt = current + step
        if (step > 0 and nxt > desired) or (step < 0 and nxt < desired):
            nxt = desired
        await self._apply_intensity(nxt)

    def _effective_target(self) -> int:
        now = time.monotonic()
        if self.state.override_value is not None and now < self.state.override_until:
            return self._clamp(self.state.override_value)
        if self.state.override_value is not None and now >= self.state.override_until:
            self.state.override_value = None
            self._log("SESSION", "override expired")
        return self.state.target_intensity

    async def _device_loop(self) -> None:
        while not self._stop_event.is_set() and self.state.active:
            if (self.coordinator is None or not self.coordinator.autonomous_allowed()
                    or self._stop_generation != self.coordinator.stop_generation):
                self.state.last_error = "Движение запрещено или аварийно остановлено"
                self._stop_event.set()
                break
            now = time.monotonic()
            if now - self.state.started_at >= self.session_max_seconds:
                self._log("SESSION", "max duration reached")
                self.state.ending = True
                break
            if now >= self.state.segment_ends_at:
                if self._maybe_advance_phase():
                    self.state.ending = True
                    break
                await self._arm_segment()
            await self._ramp_toward(self._effective_target())
            await asyncio.sleep(0.4)

    async def _generate_line(self) -> str:
        intensity = self.state.applied_intensity
        connected = self.state.device_ready
        active_source = "autonomous"
        try:
            live = await self._device_status()
            data = getattr(live, "data", None) or {}
            if getattr(live, "success", False):
                intensity = int(round(float(data.get("value", intensity))))
                connected = bool(data.get("connected", connected))
                active_source = str(data.get("active_source") or active_source)
                self.state.applied_intensity = intensity
        except Exception:
            pass

        phase = self.state.phase
        role = self.state.role
        system = (
            OPERATIONAL_PROMPTS.get(role, OPERATIONAL_PROMPTS["default"]) + "\n"
            f"Фаза: {phase}. Интенсивность сейчас: {intensity}% (макс {self.max_intensity}%)."
        )
        system += (
            f"\nФактический статус: цель {self.state.target_intensity}%, команда {intensity}%, "
            f"Intiface {'подключён' if connected else 'отключён'}, источник {active_source}. "
            "Оцени текущий статус и согласуй с ним реплику. Не выдумывай физическую обратную связь устройства."
        )

        # Role-based monologue seed
        monologue_seed = MONOLOGUE_SEEDS.get(role, {}).get(phase, MONOLOGUE_SEEDS["default"].get(phase, ""))
        system += (
            f"\nДля этой реплики используй смысловой импульс: {monologue_seed} "
            "Не копируй его дословно: продолжи, переформулируй или замени по фактическому статусу."
        )

        try:
            response = await asyncio.wait_for(
                self._chat(
                    [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": f"Реплика #{self.state.monologue_count + 1}. Только текст.",
                        },
                    ]
                ),
                timeout=8.0,
            )
            text = (getattr(response, "text", None) or "").strip()
            if getattr(response, "error", None) or not text:
                return ""
            text = " ".join(text.split())
            if len(text) > 180:
                cut = text[:181]
                boundary = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
                text = cut[: boundary + 1] if boundary >= 30 else cut.rstrip() + "…"
            return text
        except Exception:
            return ""

    async def _prefetch_loop(self) -> None:
        await asyncio.sleep(0.5)
        while not self._stop_event.is_set() and self.state.active:
            if self._line_queue.full():
                await asyncio.sleep(0.4)
                continue
            line = await self._generate_line()
            if self._stop_event.is_set() or not self.state.active:
                break
            if not line:
                await asyncio.sleep(1.0)
                continue
            try:
                self._line_queue.put_nowait(line)
            except asyncio.QueueFull:
                await asyncio.sleep(0.2)

    async def _speech_loop(self) -> None:
        await asyncio.sleep(1.5)
        while not self._stop_event.is_set() and self.state.active:
            try:
                line = await asyncio.wait_for(self._line_queue.get(), timeout=10.0)
            except asyncio.TimeoutError:
                continue
            if self._stop_event.is_set() or not self.state.active:
                break
            self.state.monologue_count += 1
            console.print(f"[yellow]MONOLOGUE:[/yellow] {line}")
            self._log("MONOLOGUE", line)
            await self._speak(line)
            wait = max(5.0, self.monologue_interval)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                continue

    async def _run_loops(self) -> None:
        console.print("[bold magenta]Autonomous session RUNNING[/bold magenta]")
        tasks = [asyncio.create_task(loop()) for loop in
                 (self._device_loop, self._speech_loop, self._prefetch_loop)]
        try:
            # DEPRECATED by Codex: gather waited forever after the device loop ended.
            finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in finished:
                task.result()
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            was_ending = self.state.ending
            self.state.active = False
            await self._force_zero()
            await asyncio.gather(*tasks, return_exceptions=True)
            console.print("[bold magenta]Autonomous session STOPPED[/bold magenta]")
            if was_ending and not self._stop_event.is_set():
                try:
                    role = self.state.role
                    if role == "госпожа":
                        await self._speak("Хватит на этот круг, Госпожа. Можете включить снова — я не наспрашивалась.")
                    elif role == "хозяйка":
                        await self._speak("Сессия завершена, Хозяйка. Готова к новым командам.")
                    elif role == "девушка":
                        await self._speak("Всё готово, милая. Можно продолжить, когда захотите.")
                    else:
                        await self._speak(" Сессия завершена. Можно начать заново.")
                except Exception:
                    pass
            self._stop_event.set()

    def status_text(self) -> str:
        if not self.active:
            role = self.state.role
            if role == "госпожа":
                return "Автономная сессия выключена, Госпожа."
            elif role == "хозяйка":
                return "Сессия завершена, Хозяйка."
            elif role == "девушка":
                return "Готова к новым командам, милая."
            else:
                return "Автономная сессия выключена."

        elapsed = int(time.monotonic() - self.state.started_at)
        ov = ""
        if self.state.override_value is not None and time.monotonic() < self.state.override_until:
            left = int(self.state.override_until - time.monotonic())
            ov = f" override {self.state.override_value}% ещё {left}с;"
        mouse_mode = " (мышь ВКЛ)" if self.state.mouse_mode else ""
        return (
            f"Сессия {elapsed}с, фаза «{self.state.phase}», "
            f"цель {self.state.target_intensity}%, сейчас {self.state.applied_intensity}%, "
            f"реплик {self.state.monologue_count}.{ov}{mouse_mode}"
            + (f" Ошибка: {self.state.last_error}" if self.state.last_error else "")
        )
