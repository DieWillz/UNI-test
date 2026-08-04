"""Демо-сценарий «мышь как человек»: Юни водит курсором плавно и с душой.

Запуск: python -m uni --demo mouse

Показывает человеко-подобное движение (minimum-jerk + Безье + overshoot)
через SmoothMouseDriver и подпись «🖱️ Uni» рядом с курсором
(CursorLabelOverlay из uni.motion.label — вспышка на клике вместо отдельного окна).

Безопасность: pyautogui.FAILSAFE (из HumanMouseController) — увод мыши в
левый верхний угол прерывает демо. Esc/стоп через driver.cancel() не нужен
для демо, но метод есть.
"""

from __future__ import annotations

import asyncio
import logging

from uni.config import AppConfig
from uni.motion import CursorLabelConfig, CursorLabelOverlay, SmoothMouseDriver
from uni.human_motion import build_heart_path, build_spiral_path

logger = logging.getLogger(__name__)


class MouseShow:
    def __init__(self, config: AppConfig) -> None:
        label_cfg = CursorLabelConfig(text="🖱️ Uni")
        self.overlay = CursorLabelOverlay(label_cfg)
        # SmoothMouseDriver теперь фасад над HumanMouseController; label для вспышек.
        self.mouse = SmoothMouseDriver(label=self.overlay)

    async def run(self) -> None:
        self.overlay.start()
        self.overlay.show()
        try:
            w, h = self.mouse.screen_size
            await self.mouse.wiggle(amplitude=24, times=3)
            self.overlay.set_text("🖱️ Uni гуляет")
            await self.mouse.wander((40, 40, w - 80, h - 80), duration=8.0)
            self.overlay.set_text("🖱️ Uni рисует спираль")
            cx, cy = w // 2, h // 2
            await self.mouse.draw(build_spiral_path((cx, cy), min(w, h) * 0.3, turns=3.0), duration=7.0)
            self.overlay.set_text("🖱️ Uni рисует ♥")
            await self.mouse.draw(build_heart_path((cx, cy), min(w, h) * 0.02), duration=7.0)
            self.overlay.set_text("🖱️ Uni")
            # верификация ±5px — показываем, что финишируем ровно в цели
            ok = await self.mouse.move_to(cx, cy)
            logger.info("move_to center verified=%s", ok)
        except Exception as exc:  # noqa: BLE001 — failsafe/прерывание
            logger.warning("Демо мыши прервано: %s", exc)
        finally:
            self.overlay.hide()
            self.overlay.stop()


async def run_mouse_demo(config: AppConfig) -> None:
    scenario = MouseShow(config)
    await scenario.run()
