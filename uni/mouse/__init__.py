"""Мышь Юни: точное управление + поиск иконок через внешний VLM (Moondream2).

ВАЖНО (Hermes, 2026-08-14):
- НЕ создаём второго HumanMouseController — используем уже существующий
  uni.capabilities.human_mouse.HumanMouseController (создан Claude, интегрирован
  в computer.py / routers_desktop.py). Здесь только надстройки: поиск иконок
  через внешний Moondream-endpoint и неблокирующая визуальная подсветка.
- Модель НЕ грузится в процесс Юни: Moondream2 запущен отдельно (Pinokio/
  imageGram), мы дёргаем его по HTTP. Синглтоны ЛЕНИВЫЕ — импорт этого
  пакета не инициирует сетевые вызовы и не грузит ничего тяжёлого.
"""

from __future__ import annotations

from .icon_finder import IconFinder
from .visual_feedback import VisualFeedback
from .browser_automation import BrowserAutomation

__all__ = ["IconFinder", "VisualFeedback", "BrowserAutomation"]


# 🤖 Ленивые синглтоны (Hermes, 2026-08-14): не создаём при import, чтобы не
# инициировать сеть/зависимости при pytest и старте Юни. Вызывай get_*() там,
# где реально нужно.
_icon_finder: IconFinder | None = None
_visual_feedback: VisualFeedback | None = None
_browser_automation: BrowserAutomation | None = None


def get_icon_finder() -> IconFinder:
    global _icon_finder
    if _icon_finder is None:
        _icon_finder = IconFinder()
    return _icon_finder


def get_visual_feedback() -> VisualFeedback:
    global _visual_feedback
    if _visual_feedback is None:
        _visual_feedback = VisualFeedback()
    return _visual_feedback


def get_browser_automation() -> BrowserAutomation:
    global _browser_automation
    if _browser_automation is None:
        _browser_automation = BrowserAutomation()
    return _browser_automation
