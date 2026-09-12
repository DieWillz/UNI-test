from __future__ import annotations

import re

_DEVICE_MARKERS = ("xtoys", "икстойс", "игруш", "интенсивност", "мощност", "intiface", "dorch")
_ACTION_MARKERS = (
    "открой", "запусти", "найди", "скачай", "сохрани", "напиши", "введи",
    "заполни", "нажми", "прикрепи", "загрузи", "переименуй", "скопируй",
    "перемести", "создай", "удали", "open", "find", "download", "save",
    "type", "fill", "click", "upload", "rename", "copy", "move", "create",
)
_SEQUENCE_MARKERS = (" и ", " затем ", " потом ", " после этого ", ", и ", ";")
_COMPLEX_MARKERS = ("скачай", "сохрани", "прикрепи", "загрузи", "переименуй",
                    "скопируй", "перемести", "создай файл", "download", "upload", "save")
# Простые команды запуска/открытия — один маркер достаточно, чтобы попасть в Operator.
# Это покрывает «открой Пуск», «открой Paint», «открой сайт X», «запусти блокнот».
_LAUNCH_MARKERS = ("открой", "запусти", "откройте", "запустить", "open", "launch", "start")
# Маркеры контекста существующего окна/браузера — явное указание на "моё окно", "открытый браузер".
_COMPUTER_CONTEXT_MARKERS = ("в моём", "в моем", "открытом", "браузере", "окне", "существующем", "моём", "моем")


def looks_like_operator_task(text: str) -> bool:
    """Conservative router: computer work goes to Operator, conversation stays in chat.

    Rules (in order):
    1. Device commands (XToys, Intiface) never go through the general Operator.
    2. Multi-step sequences with >= 2 action markers -> Operator.
    3. Single action + complex marker (download, save, upload) -> Operator.
    4. Simple launch command ("открой X", "запусти Y") -> Operator,
       unless the target is a known visual-only fallback (e.g. "открой блокнот").
    """
    normalized = " ".join((text or "").casefold().split())
    if not normalized or any(marker in normalized for marker in _DEVICE_MARKERS):
        return False
    actions = sum(1 for marker in _ACTION_MARKERS if re.search(rf"(?<!\w){re.escape(marker)}", normalized))
    if actions >= 2 and any(marker in normalized for marker in _SEQUENCE_MARKERS):
        return True
    if actions >= 1 and any(marker in normalized for marker in _COMPLEX_MARKERS):
        return True
    # An explicit existing-window/browser context makes a single UI action unambiguous.
    if actions >= 1 and any(marker in normalized for marker in _COMPUTER_CONTEXT_MARKERS):
        return True
    # Simple launch: one launch marker -> Operator.
    if any(marker in normalized for marker in _LAUNCH_MARKERS):
        return True
    return False
