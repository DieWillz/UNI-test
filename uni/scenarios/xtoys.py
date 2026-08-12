"""Демо-сценарий: Uni открывает xtoys в браузере и играет с игрушками плавной мышкой.

Запуск: python -m uni --demo xtoys

Адаптировано под РЕАЛЬНЫЙ код репозитория (ТЗ описывал вымышленный
BrowserCapability(headless=False) и config.demo.xtoys, которых нет):
  * берёт готовый Agent (он уже собрал browser/computer/xtoys/speech/vision
    как capability), а не строит их руками;
  * url xtoys берётся из config.capabilities.xtoys.url (demo.xtoys.url —
    переопределение, по умолчанию пусто);
  * интенсивность НЕ превышает max_intensity и verified_physical остаётся
    False (устройство не активируется автономно — гейт безопасности).

Безопасность:
  🔒 failsafe: pyautogui.FAILSAFE=True (из SmoothMouseDriver) — увод мыши
    в левый верхний угол гасит оверлей и чисто завершает демо.
  🔒 XToys: ramp идёт 0 → ~25% → 0, не выше max_intensity (по умолч. 50).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from uni.motion import CursorLabelConfig, CursorLabelOverlay, SmoothMouseDriver

if TYPE_CHECKING:
    from uni.config import AppConfig
    from uni.agent import Agent

logger = logging.getLogger(__name__)


class XToysScenario:
    """xtoys + браузер + плавная мышка с табличкой «Uni»."""

    def __init__(self, agent: "Agent", config: "AppConfig") -> None:
        self.agent = agent
        self.config = config
        demo = config.demo
        caps = agent.capabilities
        self.browser = caps.get("browser")
        self.xtoys = caps.get("xtoys")
        self.computer = caps.get("computer")
        self.speech = caps.get("speech")
        self.mouse = SmoothMouseDriver(
            failsafe=demo.mouse.failsafe,
            speed=demo.mouse.speed,
            fps=demo.mouse.fps,
        )
        self.overlay = CursorLabelOverlay(CursorLabelConfig(text=demo.mouse.label_text))

    async def run(self) -> None:
        demo = self.config.demo
        url = demo.xtoys.url or self.config.capabilities.xtoys.url
        self.overlay.start()
        self.overlay.show()
        try:
            await self._say("Привет! Это мышка Uni. Открываю xtoys — сейчас поиграем с игрушками.")
            if self.browser is None or self.xtoys is None:
                await self._say("Браузер или xtoys недоступны — завершаю демо.")
                return
            await self.xtoys.open()
            await asyncio.sleep(1.5)

            w, h = self.mouse.screen_size
            await self.mouse.wiggle()
            self.overlay.set_text("Uni играет")

            await self._say("Плавно вожу мышкой по игрушкам.")
            await self.mouse.wander((40, 40, w - 80, h - 80), duration=demo.xtoys.wander_seconds)

            await self._say("Теперь поглажу каждую игрушку.")
            await self._pet_toys(points=demo.xtoys.pet_points)

            # Безопасный ramp интенсивности: 0 -> скромно -> 0.
            # НЕ выше max_intensity; verified_physical не включаем.
            target = min(25, self.config.capabilities.xtoys.max_intensity)
            if self.xtoys is not None and target > 0:
                await self.xtoys.ramp_intensity("", target, steps=4)
                await asyncio.sleep(1.0)
                await self.xtoys.ramp_intensity("", 0, steps=4)

            self.overlay.set_text(self.config.demo.mouse.label_text)
            await self._say("Готово! Игрушки поглажены, мышка Uni довольна.")
        except Exception as exc:  # noqa: BLE001 — failsafe/прерывание не должно крашить
            logger.warning("Демо xtoys прервано: %s", exc)
            await self._say("Останавливаюсь.")
        finally:
            self.overlay.hide()
            self.overlay.stop()

    # ---------- помощники ----------
    async def _say(self, text: str) -> None:
        logger.info("UNI → %s", text)
        if self.speech is not None:
            try:
                await self.speech.speak(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ошибка TTS: %s", exc)

    async def _pet_toys(self, *, points: int) -> None:
        w, h = self.mouse.screen_size
        for i in range(points):
            px = w * ((i + 0.5) / points)
            py = h * (0.35 if i % 2 == 0 else 0.65)
            await self.mouse.move_to(px, py)
            await asyncio.sleep(0.5)  # дать игрушке/странице среагировать
            if self.computer is not None and i % 2 == 0:
                try:
                    await self.computer.click(int(px), int(py))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Клик не удался: %s", exc)


async def run_xtoys_demo(config: "AppConfig", agent: "Agent | None" = None) -> None:
    from uni.agent import Agent

    own_agent = agent is None
    if agent is None:
        agent = Agent(config)
        await agent.initialize()
    try:
        scenario = XToysScenario(agent, config)
        await scenario.run()
    finally:
        if own_agent:
            await agent.shutdown()
