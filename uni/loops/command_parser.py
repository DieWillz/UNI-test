"""Парсер прямых команд (P-06, извлечено из event_loop.py).

Чистые функции без self-зависимостей. Можно тестировать изолированно.
Оригинальный parse_direct_command() в EventLoop остаётся для обратной
совместимости; этот модуль — единый источник истины (EventLoop
делегатирует сюда при UNI_EVENTLOOP_MODULAR=1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DirectCommand:
    action: str
    args: dict[str, Any]


HELP_TEXT = (
    "Команды: открой XToys; интенсивность 20; выключи игрушку; подключи игрушку; паттерн wave; "
    "статус XToys; найди в интернете запрос; открой сайт example.com; "
    "что на вкладке; сделай скриншот; посмотри через камеру; "
    "смотри через камеру 10 минут; перестань смотреть в камеру; "
    "полёт фантазии про тему; выход."
)


# --- precompiled regexes ----------------------------------------------------

_AUDIO_MSG_RE = re.compile(
    r"^(?:создай|сделай|запиши)\s+(?:голосовое|аудио(?:сообщение|послание)?|послание)"
    r"(?:\s+в\s+формате\s+)?\s*(?P<format>mp3|wav)?\s*[:—-]\s*(?P<text>.+)$",
    re.IGNORECASE,
)

_MESSAGE_RE = re.compile(
    r"^(?:пусть\s+юни\s+)?(?:подготовь|напиши)\s+(?:сообщение\s+)?(?:для\s+контакта\s+)?(?P<contact>[а-яёa-z0-9_ -]{1,80})\s*[:—-]\s*(?P<text>.+)$",
    re.IGNORECASE,
)

_XTOYS_RE = re.compile(
    r"(?:xtoys|xtois|x[\s-]*(?:toys|twice|2)|xpress(?:\.app)?|"
    r"икс\s*(?:тойс|туйс|твайс)|экс\s*тойс|икстойс)"
)

_IMAGE_SEARCH_RE1 = re.compile(
    r"^(?:найди|поищи|поиск(?:ай)?|покажи)(?:\s+в\s+интернете)?\s+(?:среди\s+картинок|картинки|изображения|фото(?:графии)?)\s+(.+)$",
    re.IGNORECASE,
)
_IMAGE_SEARCH_RE2 = re.compile(
    r"^(?:найди|поищи|поиск(?:ай)?|покажи)(?:\s+в\s+интернете)?\s+(.+?)\s+(?:среди\s+картинок|в\s+картинках|в\s+изображениях)$",
    re.IGNORECASE,
)

_WEB_SEARCH_RE = re.compile(
    r"^(?:найди|поищи|поиск(?:ай)?)(?:\s+в\s+интернете|\s+в\s+сети)?\s+(.+)$",
    re.IGNORECASE,
)

_URL_RE = re.compile(
    r"^(?:открой|перейди(?:\s+на)?)(?:\s+сайт)?\s+((?:https?://)?[\w.-]+\.[a-zа-я]{2,}(?:/\S*)?)$",
    re.IGNORECASE,
)

_INTENSITY_RE = re.compile(r"(?:интенсивност\w*|мощност\w*|скорост\w*)\D{0,30}(\d{1,3})")
_PATTERN_RE = re.compile(r"(?:паттерн|режим)\s+(.+)$", re.IGNORECASE)
_IMAGINATION_RE = re.compile(
    r"(?:пол[её]т\s+фантазии|пофантазируй|самостоятельно\s+поисследуй)(?:\s+(?:про|на тему))?\s*(.*)$",
    re.IGNORECASE,
)


# --- public API -------------------------------------------------------------

def parse_direct_command(text: str) -> DirectCommand | None:
    """Возвращает DirectCommand или None (тогда передаётся в free-form LLM)."""
    original = text.strip()
    lowered = original.lower().strip(" .!?,-")
    mentions_xtoys = bool(_XTOYS_RE.search(lowered))

    if lowered in {"помощь", "что ты умеешь", "команды"}:
        return DirectCommand("internal.help", {})
    if lowered in {"да отправляй", "отправляй", "подтверждаю отправку", "да, отправь"}:
        return DirectCommand("internal.confirm_send", {})

    m = _AUDIO_MSG_RE.match(original)
    if m:
        return DirectCommand("internal.create_audio_message", {
            "text": m.group("text").strip(),
            "format": (m.group("format") or "wav").casefold(),
        })

    if "камер" in lowered and any(p in lowered for p in ("перестань", "хватит", "останови", "выключи")):
        return DirectCommand("internal.camera_stop", {})

    if "камер" in lowered and re.search(r"\b(?:смотри|наблюдай|следи)\b", lowered):
        duration_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(секунд\w*|минут\w*|час\w*)", lowered)
        seconds: float | None = None
        if "полчас" in lowered:
            seconds = 1800.0
        elif duration_match:
            amount = float(duration_match.group(1).replace(",", "."))
            unit = duration_match.group(2)
            seconds = amount * (3600 if unit.startswith("час") else 60 if unit.startswith("мин") else 1)
        elif re.search(r"(?:^|\s)(?:один\s+)?час(?:\s|$)", lowered):
            seconds = 3600.0
        return DirectCommand("internal.camera_watch", {"seconds": seconds})

    if "камер" in lowered and any(p in lowered for p in (
        "посмотри", "погляди", "оглядись", "что у меня", "что видно", "запусти", "включи", "открой",
    )):
        return DirectCommand("internal.camera_look", {})

    m = _MESSAGE_RE.match(original)
    if m:
        contact = m.group("contact").strip()
        if contact.casefold() == "асе":
            contact = "Ася"
        return DirectCommand("internal.draft_message", {"contact": contact, "text": m.group("text").strip()})

    if mentions_xtoys and any(w in lowered for w in ("открой", "открывай", "покажи", "перейди")):
        return DirectCommand("xtoys.open", {})

    if any(p in lowered for p in ("ничего не меняет", "ничего не меняется", "не сработало", "не работает")):
        return DirectCommand("internal.retry_intensity_visual", {})

    m = _IMAGINATION_RE.match(original)
    if m:
        topic = m.group(1).strip() or "необычные природные явления"
        return DirectCommand("internal.explore", {"topic": topic})

    m = _INTENSITY_RE.search(lowered)
    if m:
        return DirectCommand("xtoys.set_intensity", {"value": int(m.group(1))})
    if any(w in lowered for w in ("интенсивност", "мощност", "скорост")):
        return DirectCommand("internal.response", {
            "text": "Назовите конкретное значение от 0 до защитного максимума, например: интенсивность 5."
        })

    m = _PATTERN_RE.match(original)
    if m:
        return DirectCommand("xtoys.select_pattern", {"pattern": m.group(1).strip()})

    if mentions_xtoys and any(w in lowered for w in ("статус", "состояние", "что с")):
        return DirectCommand("xtoys.get_status", {})
    if "выключи игруш" in lowered:
        return DirectCommand("xtoys.set_intensity", {"value": 0})
    if "включи игруш" in lowered:
        return DirectCommand("internal.response", {"text": "Назовите безопасную интенсивность, например: интенсивность 10"})
    if any(w in lowered for w in ("подключи игруш", "переключи игруш")):
        return DirectCommand("xtoys.toggle", {})

    m = _IMAGE_SEARCH_RE1.match(original) or _IMAGE_SEARCH_RE2.match(original)
    if m:
        return DirectCommand("browser.search_images", {"query": m.group(1).strip()})

    m = _WEB_SEARCH_RE.match(original)
    if m:
        return DirectCommand("browser.search_web", {"query": m.group(1).strip()})

    m = _URL_RE.match(original)
    if m:
        return DirectCommand("browser.navigate", {"url": m.group(1)})

    if any(p in lowered for p in (
        "что на экране", "что на вкладке", "опиши экран", "посмотри экран",
        "посмотри на экран", "посмотри вкладку", "скажи что ты видишь", "скажи, что ты видишь",
    )):
        return DirectCommand("vision.analyze_screen", {"prompt": original})
    if any(p in lowered for p in ("сделай скриншот", "сними экран", "сохрани скриншот")):
        return DirectCommand("browser.save_screenshot", {"label": "manual"})
    if any(p in lowered for p in ("какая вкладка", "текущая вкладка", "где мы в браузере")):
        return DirectCommand("browser.current_tab", {})
    if any(p in lowered for p in ("следи за экраном", "наблюдай за экраном")):
        return DirectCommand("internal.watch_screen", {})
    if any(p in lowered for p in ("перестань следить за экраном", "хватит следить за экраном", "останови наблюдение")):
        return DirectCommand("internal.watch_screen_stop", {})
    return None


_STOP_TOKENS = (
    "стоп", "красный", "аварийный стоп", "выход", "остановись",
    "немедленно стой", "заверши работу", "пока", "exit", "quit",
)


def is_stop_command(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    return any(token in normalized for token in _STOP_TOKENS)
