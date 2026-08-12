"""Desktop Companion — проактивность: детектор событий + бюджет инициатив (D-13/D-14).

Аддитивный модуль для оверлея. Не трогает WebUI 8787 — используется из server.py
через новые эндпоинты /api/desktop/suggest и /api/desktop/act. Логика локальная,
без обращения к внешним сервисам.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_STATE_PATH = Path(__file__).resolve().parent / "state.json"

# Ключевые слова для эвристического детектора событий
_ERROR_WORDS = ("error", "ошибка", "failed", "сбой", "exception", "не удалось", "denied", "отказано")
_DIALOG_WORDS = ("dialog", "диалог", "confirm", "подтверд", "разрешить", "allow", "allow access", "do you want")
_IDLE_WORDS = ("idle", "простой", "waiting", "ожидание")

# Белый список действий для уровня act (D-14): только безопасные операции
ACTION_WHITELIST = {
    "open_app": "открыть приложение из белого списка",
    "click_ok": "нажать OK/Продолжить в диалоге",
    "type_text": "ввести текст в активное поле",
    "scroll_down": "прокрутить вниз",
    "minimize": "свернуть окно",
}


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    try:
        _STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def detect_event(caption: str) -> str | None:
    """Возвращает тип события или None. Эвристика по ключевым словам (D-13)."""
    c = (caption or "").lower()
    if any(w in c for w in _ERROR_WORDS):
        return "error"
    if any(w in c for w in _DIALOG_WORDS):
        return "dialog"
    if any(w in c for w in _IDLE_WORDS):
        return "idle"
    return None


def _quiet_hours(now_hour: int) -> bool:
    """Тихие часы: 23:00–07:00 по умолчанию (настраивается в state.quiet_hours)."""
    st = _load_state()
    qh = st.get("quiet_hours") or [23, 0, 1, 2, 3, 4, 5, 6, 7]
    return now_hour in qh


def budget_ok(limit_per_hour: int = 6) -> bool:
    """Проверка бюджета инициатив: не чаще N в час + не в тихие часы (D-13)."""
    now = time.localtime()
    if _quiet_hours(now.tm_hour):
        return False
    st = _load_state()
    hist = st.get("initiative_history", [])
    now_ts = time.time()
    # оставляем только за последний час
    hist = [t for t in hist if now_ts - t < 3600]
    if len(hist) >= limit_per_hour:
        return False
    hist.append(now_ts)
    st["initiative_history"] = hist[-50:]
    _save_state(st)
    return True


def suggest(caption: str, limit_per_hour: int = 6) -> dict:
    """D-13: детектор событий → инициатива с бюджетом.

    Возвращает {"initiative": bool, "event": str|null, "text": str|null, "reason": str}.
    """
    ev = detect_event(caption)
    if ev is None:
        return {"initiative": False, "event": None, "text": None, "reason": "no_event"}
    if not budget_ok(limit_per_hour):
        return {"initiative": False, "event": ev, "text": None, "reason": "budget_or_quiet"}
    # формируем текст инициативы по типу события
    texts = {
        "error": "Вижу ошибку на экране. Помочь разобраться?",
        "dialog": "Открыт диалог подтверждения. Подсказать, что выбрать?",
        "idle": "Похоже, ты ждёшь. Чем займёмся?",
    }
    return {"initiative": True, "event": ev, "text": texts.get(ev, "Что-то заметила на экране."),
            "reason": "ok"}


def act_allowed(action: str) -> bool:
    """D-14: проверка, что действие в белом списке."""
    return action in ACTION_WHITELIST
