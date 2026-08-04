# MVP: UNI + XToys + Browser + Mouse Control

## Цель

Создать работающее демо, где UNI:
1. Открывает браузер (Yandex / Chrome) через CDP.
2. Плавно перемещает мышь по экрану с видимой подписью «🖱️ Uni».
3. Управляет XToys-устройствами мышкой на экране или через WebSocket-команды.
4. Всё управляется голосом / текстом через единый интерфейс (WebUI / чат).

Отличный и супер-прагматичный поворот для MVP! Фокусировка на **xToys + управление браузером + реалистичное движение мышкой** дает мгновенно видимый, эффектный результат и убирает абстракцию.

Сделаем подпись курсора (аккуратный оверлей/тэг **`UNI Mouse`**), а также естественные траектории движения (кривые Безье с небольшой вариацией скорости), чтобы управление смотрелось органично.

Ниже — обновленный план и архитектура этого MVP.

---

## 🎯 Новая цель MVP: UNI xToys & Browser Driver

**Суть:** Модуль UNI берет задачу, открывает браузер, визуализирует свой курсор (кастомный каретка-тэг **`UNI`**) и плавно выполняет действия (клик/ввод/интеграция с xToys API/WebUI).

---

## 🏗️ Архитектура MVP (3 базовых блока)

```text
[ UNI Core / Decision ]
       │
       ├───> 1. xToys Connector (API / Web Socket)
       │      └─ Передача команд, статусов и триггеров
       │
       └───> 2. Human-like Mouse Engine (Bezier Trajectories)
              └─ Расчет плавных кривых, ускорения/замедления
              └─ Оверлей-указатель: "🖱️ UNI"
       │
       └───> 3. Browser Automation Controller (Playwright / CDP)
              └─ Навигация, клики, заполнение полей

```

---

## 🛠️ Технические детали реализации

### 1. Плавная мышь (Human-like Mouse Curve)

Вместо мгновенного прыжка координат (`page.mouse.move(x, y)`):

* Используем **кривые Безье (Bezier Curves)** с добавлением легкого шума (микро-колебаний человеческой руки).
* **Динамическая скорость:** ускорение в середине пути, замедление при приближении к цели (Fitts's Law).
* **Визуализация:** Иньекция в страницу небольшого стилизованного слоя:
```html
<div id="uni-cursor" style="
    position: absolute; 
    pointer-events: none; 
    z-index: 999999;
    transition: transform 0.05s ease;">
  <svg width="18" height="18">...</svg>
  <span style="
      background: #FF8C00; 
      color: #000; 
      font-family: monospace; 
      font-size: 10px; 
      font-weight: bold;
      padding: 2px 5px; 
      border-radius: 4px;
      margin-left: 12px;">UNI Mouse</span>
</div>

```



### 2. Управление браузером

* Подключение через **Playwright** или напрямую к открытому Chrome по **CDP (Chrome DevTools Protocol)**.
* Контроль элементов: наведение -> пауза 100-200ms -> клик / ввод текста с имитацией задержек между клавишами.

### 3. Интеграция с xToys

* **API / WebSocket клиент:** отправка и прием событий xToys (интенсивность, паттерны, статусы подключения).
* Отражение состояния xToys прямо в консоли UNI (например, в блоке «Состояние проекта» или отдельным виджетом).

---

## 📋 План ближайших шагов (Roadmap)

1. **Шаг 1: Скрипт плавного курсора (`uni_mouse.py`)**
* Написать генератор плавных координат и инъекцию CSS/JS-курсора `UNI Mouse`.


2. **Шаг 2: Модуль браузера (`browser_driver.py`)**
* Связать курсор с действиями клика/скролла/ввода в реальном браузере.


3. **Шаг 3: Модуль xToys (`xtoys_bridge.py`)**
* Настроить базовую авторизацию / WebSocket connection с xToys для передачи команд.


4. **Шаг 4: Вывод статуса в интерфейс UNI**
* Добавить в WebUI компактный индикатор: `xToys: Connected 🟢` и координаты мыши `UNI Mouse: [x: 450, y: 320]`.



---

Готов подготовить первый базовый скрипт для плавного движения курсора с подписью **UNI Mouse** и интеграцией с Playwright/CDP. Начинаем с него?

Отлично, фиксирую разворот MVP. Новая цель:

## 🧸 MVP «Игрушки Uni»

**Агент открывает xtoys в браузере, играет с игрушками плавно водимой мышкой, а рядом с курсором висит табличка «Uni», чтобы всем было понятно, кто тут хозяйничает.**

Обновлённый Definition of Done:

- [ ] Рядом с курсором плавно следует табличка «Uni»
- [ ] Курсор двигается по Бежье с разгоном/торможением, без телепортации
- [ ] `python -m Uni --demo xtoys` открывает xtoys в Chromium (headless=false) и «гладит» игрушки мышкой
- [ ] Uni озвучивает действия голосом (если TTS включён)
- [ ] Failsafe: мышь в левый верхний угол = аварийный стоп

Изменения в плане сборок: Build 7 расширяем hover-методами, добавляем **Build 8.5 — Smooth Mouse & Cursor Label** (параллельно с vision), Build 9 получает инструменты `mouse_drive` / `cursor_label`, а сценарий Build 10–12 меняется с «Блокнота» на «xtoys».

Архитектуру не трогаем — добавляем модули `Uni/motion/` и сценарий. Ниже код.

---

### 1. `Uni/motion/trajectory.py` — чистая математика траекторий

```python
"""Генерация плавных траекторий для курсора.

Чистые функции без побочных эффектов — легко тестировать без GUI.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]  # x, y, width, height


def clamp(value: float, lo: float, hi: float) -> float:
    """Загнать значение в [lo, hi]."""
    return max(lo, min(hi, value))


def ease_in_out_cubic(t: float) -> float:
    """Плавный разгон и торможение."""
    return 4.0 * t * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


@dataclass(frozen=True, slots=True)
class MousePath:
    """Траектория: точки + паузы (сек) после каждой точки."""

    points: tuple[Point, ...]
    delays: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.points) != len(self.delays):
            raise ValueError("points и delays должны быть одной длины")

    @property
    def duration(self) -> float:
        return sum(self.delays)


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def build_move_path(
    start: Point,
    end: Point,
    duration: float = 1.0,
    *,
    fps: int = 90,
    humanize: bool = True,
    rng: random.Random | None = None,
) -> MousePath:
    """Путь start → end: кубическая Безье + easing + микро-шум «живой руки»."""
    rng = rng or random.Random()
    dx, dy = end[0] - start[0], end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance < 1.0 or duration <= 0.0:
        return MousePath(points=(end,), delays=(max(duration, 0.02),))

    steps = int(clamp(duration * fps, 8.0, 360.0))
    # Контрольные точки у 1/3 и 2/3 отрезка, смещены по нормали.
    nx, ny = -dy / distance, dx / distance
    spread = distance * (rng.uniform(0.08, 0.22) if humanize else 0.04)
    side = rng.choice((-1.0, 1.0)) if humanize else 1.0

    def jitter() -> float:
        return rng.uniform(-4.0, 4.0) if humanize else 0.0

    c1 = (
        start[0] + dx / 3.0 + nx * spread * side + jitter(),
        start[1] + dy / 3.0 + ny * spread * side + jitter(),
    )
    c2 = (
        start[0] + 2.0 * dx / 3.0 + nx * spread * side * 0.6 + jitter(),
        start[1] + 2.0 * dy / 3.0 + ny * spread * side * 0.6 + jitter(),
    )

    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(1, steps + 1):
        points.append(_bezier(start, c1, c2, end, ease_in_out_cubic(i / steps)))
        delays.append(base_delay * (rng.uniform(0.7, 1.3) if humanize else 1.0))
    points[-1] = end  # финишируем ровно в цели
    return MousePath(points=tuple(points), delays=tuple(delays))


def build_wander_path(
    bounds: Bounds,
    duration: float = 12.0,
    *,
    fps: int = 90,
    rng: random.Random | None = None,
) -> MousePath:
    """Плавное «гуляние» внутри bounds: кривая Лиссажу со случайными параметрами."""
    rng = rng or random.Random()
    x0, y0, w, h = bounds
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    ax, ay = w * 0.42, h * 0.42
    a, b = rng.choice((1, 2, 3)), rng.choice((1, 2, 3))
    if a == b:  # не даём выродиться в эллипс
        b = a + 1
    phase = rng.uniform(0.0, math.tau)

    steps = int(clamp(duration * fps, 16.0, 4000.0))
    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(steps):
        t = math.tau * i / (steps - 1)
        points.append((cx + ax * math.sin(a * t + phase), cy + ay * math.sin(b * t)))
        delays.append(base_delay * rng.uniform(0.85, 1.15))
    return MousePath(points=tuple(points), delays=tuple(delays))


def build_circle_path(
    center: Point,
    radius: float,
    *,
    turns: float = 1.0,
    duration: float = 6.0,
    fps: int = 90,
    start_angle: float = -math.pi / 2.0,
) -> MousePath:
    """Круг/спираль вокруг center."""
    steps = int(clamp(duration * fps, 16.0, 4000.0))
    base_delay = duration / steps
    points: list[Point] = []
    delays: list[float] = []
    for i in range(steps + 1):
        angle = start_angle + math.tau * turns * i / steps
        points.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
        delays.append(base_delay)
    return MousePath(points=tuple(points), delays=tuple(delays))
```

---

### 2. `Uni/motion/driver.py` — плавный драйвер курсора

```python
"""Плавное «живое» управление курсором поверх PyAutoGUI."""

from __future__ import annotations

import asyncio
import math

import pyautogui

from Uni.motion.trajectory import (
    Bounds,
    MousePath,
    Point,
    build_circle_path,
    build_move_path,
    build_wander_path,
    clamp,
)

_MIN_FRAME_DT = 1.0 / 240.0


class SmoothMouseDriver:
    """Водит системный курсор плавно: Безье, easing, человеческий шум.

    Безопасность: при failsafe=True резкий увод курсора в левый верхний угол
    экрана прерывает работу (pyautogui.FailSafeException).
    """

    def __init__(self, *, failsafe: bool = True, speed: float = 1.0, fps: int = 90) -> None:
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0.0  # паузами рулим сами через asyncio
        self._speed = clamp(speed, 0.1, 5.0)
        self._fps = fps
        self._busy = asyncio.Lock()

    # ---------- состояние ----------
    @property
    def position(self) -> tuple[int, int]:
        x, y = pyautogui.position()
        return int(x), int(y)

    @property
    def screen_size(self) -> tuple[int, int]:
        w, h = pyautogui.size()
        return int(w), int(h)

    # ---------- API ----------
    async def move_to(
        self,
        x: float,
        y: float,
        *,
        duration: float | None = None,
        humanize: bool = True,
    ) -> None:
        """Плавно переместить курсор в точку (x, y)."""
        start = self.position
        if duration is None:
            duration = self._natural_duration(math.hypot(x - start[0], y - start[1]))
        path = build_move_path(start, (float(x), float(y)), duration, fps=self._fps, humanize=humanize)
        await self._play(path)

    async def wiggle(self, *, amplitude: int = 24, times: int = 3) -> None:
        """Помахать курсором на месте — жест «привет, это я»."""
        x, y = self.position
        for _ in range(times):
            await self.move_to(x - amplitude, y, duration=0.12, humanize=False)
            await self.move_to(x + amplitude, y, duration=0.12, humanize=False)
        await self.move_to(x, y, duration=0.12, humanize=False)

    async def circle(
        self,
        center: Point,
        radius: float,
        *,
        turns: float = 1.0,
        duration: float = 6.0,
    ) -> None:
        """Обвести курсором круг."""
        path = build_circle_path(center, radius, turns=turns, duration=duration / self._speed, fps=self._fps)
        await self._play(path)

    async def wander(self, bounds: Bounds, *, duration: float = 12.0) -> None:
        """Плавно поводить курсором внутри bounds в течение duration секунд."""
        path = build_wander_path(bounds, duration / self._speed, fps=self._fps)
        await self._play(path)

    async def click(self, x: float | None = None, y: float | None = None, *, button: str = "left") -> None:
        """Клик (опционально — сначала плавно доехать до точки)."""
        if x is not None and y is not None:
            await self.move_to(x, y)
        await asyncio.to_thread(pyautogui.click, button=button)

    async def drag_to(self, x: float, y: float, *, duration: float = 1.2) -> None:
        """Плавный драг из текущей позиции в (x, y) — пригодится для игрушек."""
        path = build_move_path(self.position, (float(x), float(y)), duration, fps=self._fps)
        async with self._busy:
            await asyncio.to_thread(pyautogui.mouseDown)
            try:
                await self._play_points(path)
            finally:
                await asyncio.to_thread(pyautogui.mouseUp)

    # ---------- внутреннее ----------
    def _natural_duration(self, distance: float) -> float:
        """«Человеческая» длительность: ~1400 px/с, ограничена [0.25, 2.5] с."""
        return clamp(distance / 1400.0, 0.25, 2.5) / self._speed

    async def _play(self, path: MousePath) -> None:
        async with self._busy:
            await self._play_points(path)

    async def _play_points(self, path: MousePath) -> None:
        for (px, py), delay in zip(path.points, path.delays):
            pyautogui.moveTo(px, py, _pause=False)
            await asyncio.sleep(max(delay / self._speed, _MIN_FRAME_DT))
```

---

### 3. `Uni/motion/label.py` — табличка «Мышка Uni»

```python
"""Табличка-подпись курсора Uni: прозрачное always-on-top окно, следующее за мышью.

tkinter живёт в отдельном потоке и не блокирует asyncio-цикл агента.
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
        import tkinter as tk

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
```

### `Uni/motion/__init__.py`

```python
from Uni.motion.driver import SmoothMouseDriver
from Uni.motion.label import CursorLabelConfig, CursorLabelOverlay
from Uni.motion.trajectory import (
    MousePath,
    build_circle_path,
    build_move_path,
    build_wander_path,
)

__all__ = [
    "SmoothMouseDriver",
    "CursorLabelConfig",
    "CursorLabelOverlay",
    "MousePath",
    "build_move_path",
    "build_wander_path",
    "build_circle_path",
]
```

---

### 4. Дополнение `Uni/capabilities/browser.py`

```python
# --- добавить в класс BrowserCapability ---

async def hover_selector(self, selector: str, *, steps: int = 30) -> None:
    """Плавно подвести «виртуальную» мышь Playwright к элементу (игрушки реагируют на hover)."""
    box = await self._page.locator(selector).bounding_box()
    if box is None:
        raise RuntimeError(f"Элемент не найден: {selector}")
    await self._page.mouse.move(
        box["x"] + box["width"] / 2.0,
        box["y"] + box["height"] / 2.0,
        steps=steps,
    )

async def viewport_size(self) -> tuple[int, int]:
    size = self._page.viewport_size or {"width": 1280, "height": 720}
    return int(size["width"]), int(size["height"])

async def viewport_screen_origin(self) -> tuple[int, int]:
    """Best-effort позиция вьюпорта на экране — чтобы наводить системный курсор на страницу.

    Внимание: предполагает масштаб Windows 100%; при другом DPI нужна калибровка.
    """
    sx = await self._page.evaluate("() => window.screenX")
    sy = await self._page.evaluate("() => window.screenY")
    return int(sx), int(sy)
```

---

### 5. `Uni/scenarios/xtoys.py` — демо-сценарий

```python
"""Демо-сценарий: Uni открывает xtoys в браузере и играет с игрушками плавной мышкой.

Запуск: python -m Uni --demo xtoys
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from Uni.capabilities.browser import BrowserCapability
from Uni.motion import CursorLabelConfig, CursorLabelOverlay, SmoothMouseDriver

if TYPE_CHECKING:
    from Uni.capabilities.speech import SpeechCapability
    from Uni.config import AppConfig

logger = logging.getLogger(__name__)


class XToysScenario:
    """xtoys + браузер + плавная мышка с табличкой «Мышка Uni»."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        demo = config.demo
        self.browser = BrowserCapability(headless=False)  # viewport берётся из config
        self.mouse = SmoothMouseDriver(
            failsafe=demo.mouse.failsafe,
            speed=demo.mouse.speed,
            fps=demo.mouse.fps,
        )
        self.overlay = CursorLabelOverlay(CursorLabelConfig(text=demo.mouse.label_text))
        self.speech: SpeechCapability | None = None
        if demo.voice_comments:
            try:
                from Uni.capabilities.speech import SpeechCapability

                self.speech = SpeechCapability()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Голосовые комментарии отключены: %s", exc)

    async def run(self) -> None:
        demo = self._config.demo.xtoys
        self.overlay.start()
        self.overlay.show()

        await self._say("Привет! Это мышка Uni. Открываю xtoys — сейчас поиграем с игрушками.")
        await self.browser.navigate(demo.url)
        await self._wait_page_ready()

        bounds = await self._page_bounds()
        await self.mouse.wiggle()
        self.overlay.set_text("Uni играет")

        await self._say("Плавно вожу мышкой по игрушкам.")
        await self.mouse.wander(bounds, duration=demo.wander_seconds)

        await self._say("Теперь поглажу каждую игрушку.")
        await self._pet_toys(bounds, points=demo.pet_points)

        self.overlay.set_text(self._config.demo.mouse.label_text)
        await self._say("Готово! Игрушки поглажены, мышка Uni довольна.")
        self.overlay.hide()

    # ---------- помощники ----------
    async def _say(self, text: str) -> None:
        logger.info("UNI → %s", text)
        if self.speech is not None:
            try:
                await self.speech.speak(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ошибка TTS: %s", exc)

    async def _wait_page_ready(self) -> None:
        try:
            await self.browser.wait_for_selector("body", timeout=15_000)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(2.0)

    async def _page_bounds(self) -> tuple[int, int, int, int]:
        """Best-effort переводим вьюпорт страницы в экранные координаты."""
        try:
            ox, oy = await self.browser.viewport_screen_origin()
            width, height = await self.browser.viewport_size()
            return int(ox), int(oy), int(width), int(height)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось получить вьюпорт (%s) — играем на весь экран", exc)
            width, height = self.mouse.screen_size
            return 0, 0, width, height

    async def _pet_toys(self, bounds: tuple[int, int, int, int], *, points: int) -> None:
        x0, y0, width, height = bounds
        for i in range(points):
            px = x0 + width * ((i + 0.5) / points)
            py = y0 + height * (0.35 if i % 2 == 0 else 0.65)
            await self.mouse.move_to(px, py)
            await asyncio.sleep(0.5)  # дать игрушке среагировать на hover
            if i % 2 == 0:
                await self.mouse.click()


async def run_xtoys_demo(config: AppConfig) -> None:
    scenario = XToysScenario(config)
    try:
        await scenario.run()
    finally:
        scenario.overlay.stop()
```

---

### 6. Конфиг

Добавить в `Uni/config.py`:

```python
class DemoMouseSettings(BaseModel):
    label_text: str = "Uni"
    speed: float = Field(default=1.0, ge=0.1, le=5.0)
    fps: int = Field(default=90, ge=30, le=240)
    failsafe: bool = True


class DemoXToysSettings(BaseModel):
    url: str = "https://xtoys.app"  # TODO: уточнить адрес xtoys
    wander_seconds: float = Field(default=12.0, ge=1.0, le=300.0)
    pet_points: int = Field(default=6, ge=1, le=32)


class DemoSettings(BaseModel):
    xtoys: DemoXToysSettings = Field(default_factory=DemoXToysSettings)
    mouse: DemoMouseSettings = Field(default_factory=DemoMouseSettings)
    voice_comments: bool = True
```

в `AppConfig` добавить поле `demo: DemoSettings = Field(default_factory=DemoSettings)`, а в `config.yaml`:

```yaml
# --- демо-сценарий «Игрушки Uni» ---
demo:
  xtoys:
    url: "https://xtoys.app"   # ← укажи реальный адрес xtoys
    wander_seconds: 12
    pet_points: 6
  mouse:
    label_text: "Uni"
    speed: 1.0          # >1 — быстрее, <1 — медленнее
    fps: 90
    failsafe: true      # аварийный стоп: курсор в левый верхний угол
  voice_comments: true
```

---

### 7. Инструменты для Brain (`Uni/tools/definitions.py`)

Чтобы мозг сам мог решать «поводить мышкой»:

```python
class MouseDriveArgs(BaseModel):
    """Плавное вождение мышки Uni."""

    mode: Literal["move", "wander", "circle", "wiggle"] = "wander"
    x: int | None = Field(default=None, description="Целевой X для mode=move")
    y: int | None = Field(default=None, description="Целевой Y для mode=move")
    duration: float = Field(default=8.0, ge=0.5, le=60.0, description="Длительность, сек")


MOUSE_DRIVE_TOOL: Final[dict] = {
    "type": "function",
    "function": {
        "name": "mouse_drive",
        "description": "Плавно повести мышку Uni: к точке, по кругу или погулять по экрану.",
        "parameters": MouseDriveArgs.model_json_schema(),
    },
}

CURSOR_LABEL_TOOL: Final[dict] = {
    "type": "function",
    "function": {
        "name": "cursor_label",
        "description": "Табличка «Мышка Uni» у курсора: показать, спрятать или сменить текст.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["show", "hide", "text"]},
                "text": {"type": "string", "description": "Новый текст для action=text"},
            },
            "required": ["action"],
        },
    },
}
```

В `executors.py` замапить `mouse_drive → SmoothMouseDriver` и `cursor_label → CursorLabelOverlay` (синглтоны создаются в `Agent` и передаются в диспетчер так же, как остальные capability).

---

### 8. CLI — флаг `--demo` в `Uni.py`

```python
parser = argparse.ArgumentParser(prog="Uni", description="Uni MVP")
parser.add_argument("--demo", choices=("xtoys",), default=None,
                    help="Запустить демо-сценарий вместо основного цикла агента")
args = parser.parse_args()

config = load_config("config.yaml")
if args.demo == "xtoys":
    from Uni.scenarios.xtoys import run_xtoys_demo

    print("🧸 Демо: Uni играет с xtoys")
    await run_xtoys_demo(config)
else:
    agent = Agent(config)
    await agent.run()
```

---

### Проверка

```bash
# 1. Траектории без GUI
python -c "from Uni.motion.trajectory import build_move_path; p = build_move_path((0,0),(800,600),1.0); print(len(p.points), round(p.duration,2))"

# 2. Мышка + табличка
python -c "
import asyncio
from Uni.motion import SmoothMouseDriver, CursorLabelOverlay

async def main():
    label = CursorLabelOverlay(); label.start(); label.show()
    m = SmoothMouseDriver()
    await m.wiggle()
    w, h = m.screen_size
    await m.wander((100, 100, w - 200, h - 200), duration=8)
    label.stop()

asyncio.run(main())
"

# 3. Полный сценарий
python -m Uni --demo xtoys
```

Два уточнения, прежде чем двигаться дальше:

1. **Точный URL xtoys** — в конфиге пока стоит плейсхолдер `https://xtoys.app`. Скажи реальный адрес, и если игрушки там требуют специфических жестов (драг, удержание) — подстрою `_pet_toys`.
2. **Масштаб Windows** — если у тебя не 100%, маппинг вьюпорта в экранные координаты может уезжать; добавлю калибровочный офсет в конфиг.

## Архитектура MVP

```

┌────────────────────────────────────────────────────────────────────────────┐
│                         UNI CORE (главный агент)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  Event Loop (asyncio)                                               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │  │
│  │  │ Speech Input │  │ TTS Output   │  │  Command Parser           │ │  │
│  │  │ (Vosk/Silero)│  │ (Silero)     │  │  (интерпретация команд)  │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                              │ (команды)                                   │
└────────────────────────────────────────────────────────────────────────────┘
▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         МОДУЛИ-ИСПОЛНИТЕЛИ                                 │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐  │
│  │  BrowserExecutor   │  │  MouseExecutor      │  │  XToysExecutor     │  │
│  │  (CDP к Yandex)     │  │  (плавное движение  │  │  (WebSocket / REST │  │
│  │                     │  │   с визуальной      │  │   к XToys)         │  │
│  │                     │  │   подписью)         │  │                     │  │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
│
▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         ВИЗУАЛЬНЫЙ ИНТЕРФЕЙС (WebUI)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  - Окно управления браузером (URL, клики, скролл)                    │  │
│  │  - Панель XToys (интенсивность, паттерны)                           │  │
│  │  - Лог действий с подписью "🖱️ Uni"                                  │  │
│  │  - Голосовое управление (mic in / speaker out)                      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘

```

---

## Компоненты и файлы

### 1. `uni/browser_executor.py` — управление браузером через CDP

```python
import asyncio
from playwright.async_api import async_playwright, Browser, Page

class BrowserExecutor:
    def __init__(self):
        self.browser: Browser = None
        self.page: Page = None
    
    async def launch(self, headless=False):
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(
            headless=headless,
            executable_path="C:/Program Files/Yandex/Browser/Application/browser.exe"  # или chrome
        )
        self.page = await self.browser.new_page()
        return self.page
    
    async def goto(self, url: str):
        await self.page.goto(url)
    
    async def click(self, selector: str):
        await self.page.click(selector)
    
    async def type(self, selector: str, text: str):
        await self.page.fill(selector, text)
    
    async def screenshot(self, path: str = "screenshot.png"):
        await self.page.screenshot(path=path)
```

### 2. `uni/mouse_executor.py` — плавное вождение мыши с подписью

```
import asyncio
import pyautogui
from typing import Tuple

class MouseExecutor:
    def __init__(self):
        self.display_label = "🖱️ Uni"
        self.speed = 0.5  # 0.1..1.0 (медленно → быстро)
    
    async def move_to(self, x: int, y: int, duration: float = 0.5):
        """Плавно перемещает мышь в (x, y) с визуальной подписью."""
        # В реальности: вызов API Windows для плавного движения
        # Здесь — PyAutoGUI с эмуляцией подписи через оверлей (см. ниже)
        pyautogui.moveTo(x, y, duration=duration)
        # Визуальная подпись: отрисовка через окно-оверлей (или уведомление)
        await self._show_label(x, y)
    
    async def _show_label(self, x: int, y: int):
        """Показывает подпись '🖱️ Uni' рядом с курсором."""
        # В MVP: используем tkinter-оверлей или Windows API
        # Пока заглушка — отправляем событие в WebUI
        pass

    async def click(self):
        pyautogui.click()
```

### 3. `uni/xtoys_executor.py` — управление XToys через WebSocket

```
import asyncio
import websockets
import json

class XToysExecutor:
    def __init__(self, ws_url: str = "ws://localhost:8000/xtoys"):
        self.ws_url = ws_url
        self.connection = None
    
    async def connect(self):
        self.connection = await websockets.connect(self.ws_url)
    
    async def send_command(self, command: dict):
        """Отправляет команду в XToys (например, вибрация)."""
        if self.connection:
            await self.connection.send(json.dumps(command))
    
    async def vibe(self, intensity: float, duration_ms: int):
        """Интенсивность 0..1, длительность в мс."""
        await self.send_command({
            "type": "vibrate",
            "intensity": intensity,
            "duration": duration_ms
        })
    
    async def pattern(self, pattern: str):
        """Отправляет паттерн (wave, pulse, tease, punish)."""
        await self.send_command({
            "type": "pattern",
            "name": pattern
        })
```

### 4. `uni/webui/app.py` — интерфейс управления

```
from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI(title="UNI XToys + Browser Control")

@app.get("/")
async def index():
    return {"message": "UNI XToys + Browser Control"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        # Обработка команд: голос, браузер, мышь, xtoys
        await websocket.send_text(f"Команда получена: {data}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8787)
```

### 5. `uni/event_loop.py` — главный цикл с интеграцией модулей

```
import asyncio
from uni.browser_executor import BrowserExecutor
from uni.mouse_executor import MouseExecutor
from uni.xtoys_executor import XToysExecutor
from uni.speech import SpeechToText, TextToSpeech

class EventLoop:
    def __init__(self):
        self.browser = BrowserExecutor()
        self.mouse = MouseExecutor()
        self.xtoys = XToysExecutor()
        self.stt = SpeechToText()
        self.tts = TextToSpeech()
    
    async def run(self):
        await self.xtoys.connect()
        await self.browser.launch(headless=False)
        
        while True:
            # 1. Слушаем голос (или WebSocket)
            command = await self.stt.listen()
            
            # 2. Парсим команду
            if "открой" in command:
                url = command.replace("открой", "").strip()
                await self.browser.goto(f"https://{url}")
                await self.tts.say(f"Открываю {url}")
            elif "кликни" in command:
                await self.browser.click("button")
                await self.tts.say("Кликнул")
            elif "мышь" in command:
                # Плавное движение мыши
                await self.mouse.move_to(100, 100)
                await self.tts.say("Мышь перемещена")
            elif "вибрация" in command:
                await self.xtoys.vibe(0.8, 2000)
                await self.tts.say("Вибрация включена")
            elif "паттерн" in command:
                pattern = command.split()[-1]
                await self.xtoys.pattern(pattern)
            else:
                await self.tts.say("Я не поняла команду")
            
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    loop = EventLoop()
    asyncio.run(loop.run())
```

### 6. `ui/index.html` — базовый WebUI с логом действий

```
<!DOCTYPE html>
<html>
<head>
    <title>UNI Control Center</title>
    <style>
        body { font-family: system-ui; background: #111; color: #eee; }
        .log { margin-top: 20px; border: 1px solid #333; padding: 10px; height: 300px; overflow-y: auto; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid #222; }
        .mouse-label { color: #0ff; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🖱️ UNI Control</h1>
    <div id="log" class="log"></div>
    <script>
        const logDiv = document.getElementById('log');
        const ws = new WebSocket('ws://localhost:8787/ws');
        ws.onmessage = (e) => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `🖱️ Uni: ${e.data}`;
            logDiv.appendChild(entry);
            logDiv.scrollTop = logDiv.scrollHeight;
        };
    </script>
</body>
</html>
```

### 7. `requirements.txt`

```
fastapi
uvicorn
websockets
playwright
pyautogui
pydantic
aiofiles
pyaudio
vosk
silero-tts
```

---

## План реализации (4 этапа)

| Этап ↕▾ | Что делаем ↕▾ | Файлы ↕▾ |
|---|---|---|
| −1 | Браузер через CDP | `browser_executor.py` |
| −2 | Плавная мышь с подписью | `mouse_executor.py` + оверлей (tkinter/Windows API) |
| −3 | XToys WebSocket | `xtoys_executor.py` |
| −4 | Интеграция в EventLoop + WebUI | `event_loop.py`, `app.py`, `index.html` |
⚙

---

## Визуальная подпись «🖱️ Uni»

Для реализации подписи рядом с курсором в MVP можно использовать:

- **Tkinter-оверлей**: прозрачное окно, которое следует за курсором.
- **Windows API**: через `ctypes` создать прозрачное окно с текстом.
- **PyQt5** — но для MVP слишком тяжело.

```
# mouse_overlay.py (заглушка)
class MouseOverlay:
    def __init__(self):
        self.label = "🖱️ Uni"
    
    def show(self, x, y):
        # В реальности — отрисовка оверлея
        print(f"🖱️ Uni at ({x}, {y})")
```

В логах WebUI подпись автоматически добавляется к каждой команде.

---

## Главный принцип MVP

> **UNI — это не просто агент, а живое существо, которое двигает мышь, управляет браузером и XToys. Всё, что она делает, подписано «🖱️ Uni».**

# ТЗ для Hermes: Реализация кода, аудиторская проверка и интеграция зрения/камеры (UNI MVP)

---

## 🎯 Контекст и задача

Необходимо дописать недостающий код, провести полный рефакторинг и аудиторскую проверку текущей кодовой базы **UNI**, а также интегрировать **модуль компьютерного зрения (Vision / Camera)** для анализа происходящего на экране и работы с веб-камерой.

MVP фокусируется на:

1. **Управлении браузером через CDP/Playwright**.
2. **Плавном физическом вождении мышки (`SmoothMouseDriver`)** по кривым Безье с плавающим оверлеем **«🖱️ Uni»**.
3. **Управлении xToys** (через браузерный UI / WebSocket / REST).
4. **Зрении (Vision & Camera)** — фиксация экрана и веб-камеры для анализа состояния.

---

## 📋 Чек-лист задач для Hermes (Task Matrix)

### Блок 1: Аудит кодовой базы и проверка Failsafe

* [ ] Проверить все импорты и циклы `asyncio`. Убедиться, что GUI Tkinter (`CursorLabelOverlay`) вынесен в отдельный поток и **не блокирует** основной `asyncio event loop`.
* [ ] Проверить работу `pyautogui.FAILSAFE = True`. При уводе мыши в левый верхний угол $(0, 0)$ система должна корректно перехватывать `pyautogui.FailSafeException`, гасить оверлей и безопасно останавливать все таски.
* [ ] Добавить обработку масштабирования Windows DPI (`SetProcessDpiAwareness(1)`), чтобы координаты Playwright, системной мыши и Tkinter-оверлея совпадали на 100%.

---

### Блок 2: Реализация недостающего модуля зрения (`Uni/vision/`)

Создать модуль `Uni/vision/` для захвата кадров с веб-камеры и экрана (пригодится для валидации состояния xToys и кликов).

#### 1. `Uni/vision/camera.py` — Захват веб-камеры и скринов

```python
"""Модуль работы с компьютерным зрением и веб-камерой."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VisionCapability:
    """Управление веб-камерой и скриншотами для анализа состояния."""

    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index

    async def capture_frame(self) -> Optional[np.ndarray]:
        """Сделать снимок с веб-камеры (асинхронная обертка)."""
        def _read_frame():
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                logger.error("Не удалось открыть веб-камеру idx=%s", self.camera_index)
                return None
            ret, frame = cap.read()
            cap.release()
            return frame if ret else None

        return await asyncio.to_thread(_read_frame)

    async def save_camera_snapshot(self, output_path: str | Path = "camera_snap.jpg") -> bool:
        """Сохранить снимок с камеры на диск."""
        frame = await self.capture_frame()
        if frame is None:
            return False
        
        def _write():
            return cv2.imwrite(str(output_path), frame)

        return await asyncio.to_thread(_write)

```

---

### Блок 3: Интеграция XToys WebSocket Client (`Uni/capabilities/xtoys_ws.py`)

Дополнить direct-управление xToys через WebSocket/REST на случай, если управление идет не только через браузерный hover/click.

```python
"""Прямой WebSocket-интерфейс к xToys (если используется xToys Desktop / Engine API)."""

from __future__ import annotations

import asyncio
import json
import logging
import websockets

logger = logging.getLogger(__name__)


class XToysWSCapability:
    def __init__(self, ws_url: str = "ws://localhost:8000/xtoys") -> None:
        self.ws_url = ws_url
        self._ws = None

    async def connect(self) -> None:
        try:
            self._ws = await websockets.connect(self.ws_url)
            logger.info("Подключено к xToys WebSocket: %s", self.ws_url)
        except Exception as exc:
            logger.warning("Не удалось подключиться к xToys WS (%s). Работаем в браузерном режиме.", exc)

    async def send_vibe(self, intensity: float, duration_ms: int) -> None:
        if self._ws:
            payload = {
                "type": "vibrate",
                "intensity": max(0.0, min(1.0, intensity)),
                "duration": duration_ms,
            }
            await self._ws.send(json.dumps(payload))

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()

```

---

### Блок 4: Интеграция в мозг и инструменты (`Uni/tools/executors.py`)

Hermes должен убедиться, что инструменты `mouse_drive`, `cursor_label` и `vision_snap` зарегистрированы в диспетчере:

```python
# Добавить в реестр инструментов
VISION_SNAP_TOOL = {
    "type": "function",
    "function": {
        "name": "vision_snap",
        "description": "Сделать снимок с веб-камеры или экрана для проверки состояния.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["camera", "screen"]},
            },
            "required": ["target"],
        },
    },
}

```

---

## 🧪 Инструкция по тестированию для Hermes

После добавления кода выполнить последовательную проверку:

```bash
# 1. Проверка траекторий и генерации Bezier
python -c "from Uni.motion.trajectory import build_move_path; p = build_move_path((0,0),(500,500), 1.0); print('Path points:', len(p.points))"

# 2. Проверка плавного движения мыши и оверлея «Uni»
python -c "
import asyncio
from Uni.motion import SmoothMouseDriver, CursorLabelOverlay

async def test():
    label = CursorLabelOverlay()
    label.start()
    label.show()
    mouse = SmoothMouseDriver()
    await mouse.wiggle()
    label.stop()

asyncio.run(test())
"

# 3. Проверка камеры
python -c "
import asyncio
from Uni.vision.camera import VisionCapability

async def test_cam():
    v = VisionCapability()
    res = await v.save_camera_snapshot('test_snap.jpg')
    print('Camera snapshot saved:', res)

asyncio.run(test_cam())
"

# 4. Запуск полного демо-сценария xToys
python -m Uni --demo xtoys

```

---

## Definition of Done (критерии приемки)

1. Команда `python -m Uni --demo xtoys` открывает браузер, подключает оверлей **«🖱️ Uni»** и осуществляет гладкие движения мыши.
2. При срабатывании Failsafe (мышь в левый верхний угол) скрипт не падаёт с критической ошибкой без очистки ресурсов (оверлей корректно скрывается).
3. Модуль камеры делает снимок без блокировки `asyncio`.
4. Весь код соответствует PEP8, аннотирован типами (`from __future__ import annotations`).


# Т
```

C:/LLM/UNI/
├── uni/
│   ├── browser_executor.py
│   ├── mouse_executor.py
│   ├── mouse_overlay.py
│   ├── camera_executor.py
│   ├── xtoys_executor.py
│   ├── xtoys_patterns.py
│   ├── event_loop.py
│   ├── webui/
│   │   ├── app.py
│   │   └── static/
│   │       ├── index.html
│   │       └── script.js
│   └── speech/
│       ├── **init**.py
│       ├── stt.py (Vosk)
│       └── tts.py (Silero)
├── tests/
│   ├── test_browser.py
│   ├── test_mouse.py
│   └── test_xtoys.py
├── requirements.txt
├── config.yaml (опционально)
└── README.md (инструкция по запуску)

```

---

## 3.
```

### 7.2. Автоматические тесты

```
#
```

### 7.3. Проверка XToys

```
# Тестовый ск
```

---

## 8. Требования к документации

Каждый модуль должен содержать:

1. **Docstring** на английском (описание класса и публичных методов).
2. **Пример использования** в виде кода.
3. **Обработка ошибок** (try/except с логированием).

---

## 9. Сроки и отчётность

- **Срок выполнения:** 5 дней.
- **Формат отчёта:**

1. Список реализованных модулей.
2. Результаты тестов (`pytest`).
3. Скриншоты работы (WebUI, оверлей, браузер).
4. Если что-то не реализовано — объяснить почему.

---

## 10. Ограничения для Hermes (обязательные)

1. **Не изменять архитектуру** без согласования.
2. **Не использовать внешние API** (только локальные модели).
3. **Не создавать дублирующие файлы** (если файл уже есть — дописывать его).
4. **Тестировать перед сдачей** (прогонять `pytest`).
5. **Не коммитить в репозиторий без явной проверки** (сначала локально, потом через PR).

```

</
