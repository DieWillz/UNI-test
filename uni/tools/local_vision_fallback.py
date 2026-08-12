"""🤖 Локальный fallback для vision: UIA + опциональный OCR (без облака/VLM).

Когда локальная VLM (LM Studio / Gradio) недоступна, управление ПК под зрением
всё равно должно работать для базовых случаев: найти кнопку/поле по имени через
UIA (Windows UI Automation) и вернуть его координаты в **логических** пикселях
(с тем же масштабом, что и скриншот vision — см. display_calibration).

Все функции ТИХО возвращают None при недоступности (не-Windows, нет библиотеки,
headless) — чтобы не ломать ядро vision.py и не ронять клики.

НЕ является capability и НЕ импортирует capability. Чистая утилита обнаружения.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _import_uiautomation():
    """Попытаться импортировать uiautomation; None если недоступно."""
    try:
        import uiautomation as uia  # type: ignore
        return uia
    except Exception as exc:  # ImportError / нет Windows COM
        logger.debug("uiautomation недоступен: %s", exc)
        return None


def uia_find_element(description: str) -> dict[str, Any] | None:
    """Найти элемент управления по описанию через UIA.

    Возвращает dict {"x","y","width","height","confidence"} в логических пикселях
    (uiautomation уже отдаёт координаты в системных/логических единицах экрана)
    или None, если не найдено / недоступно.

    Поиск: по подстроке имени (Name) или класса (ClassName) — описание на русском
    сопоставляем с ControlType ключевыми словами (кнопка/поле/ссылка/чекбокс…).
    """
    uia = _import_uiautomation()
    if uia is None:
        return None
    try:
        text = (description or "").strip().lower()
        # Сопоставление описания с ControlType UIA (на русском/английском).
        type_map = [
            ("кнопк", uia.ControlType.ButtonControl),
            ("button", uia.ControlType.ButtonControl),
            ("поле", uia.ControlType.EditControl),
            ("edit", uia.ControlType.EditControl),
            ("ввод", uia.ControlType.EditControl),
            ("ссылк", uia.ControlType.HyperlinkControl),
            ("link", uia.ControlType.HyperlinkControl),
            ("чекбокс", uia.ControlType.CheckBoxControl),
            ("checkbox", uia.ControlType.CheckBoxControl),
            ("комб", uia.ControlType.ComboBoxControl),
            ("combo", uia.ControlType.ComboBoxControl),
            ("меню", uia.ControlType.MenuControl),
            ("menu", uia.ControlType.MenuControl),
            ("текст", uia.ControlType.TextControl),
            ("text", uia.ControlType.TextControl),
        ]
        control_type = None
        for kw, ct in type_map:
            if kw in text:
                control_type = ct
                break

        # Имя для поиска — выкинем служебные слова, оставим осмысленную подстроку.
        name_hint = text
        for stop in ("открой", "кликни", "нажми", "запусти", "включи", "щёлкни",
                     "кнопка", "поле", "ссылка", "чекбокс", "элемент", "интерфейса",
                     "для", "цели", ":", "-", "button", "edit", "link", "checkbox"):
            name_hint = name_hint.replace(stop, " ")
        name_hint = name_hint.strip()
        if len(name_hint) < 2:
            name_hint = text

        from uiautomation import TreeScope  # type: ignore

        root = uia.GetRootControl()
        # Сначала ищем по имени (точнее), потом по типу.
        candidates = []
        if name_hint:
            conds = []
            if control_type is not None:
                conds.append(uia.AndCondition(
                    uia.ControlTypeCondition(control_type),
                    uia.NameCondition(name_hint, partial=True),
                ))
            else:
                conds.append(uia.NameCondition(name_hint, partial=True))
            for cond in conds:
                el = root.FindFirst(TreeScope.Descendants, cond)
                if el is not None:
                    candidates.append(el)
                    break
        if not candidates and control_type is not None:
            el = root.FindFirst(TreeScope.Descendants, uia.ControlTypeCondition(control_type))
            if el is not None:
                candidates.append(el)

        if not candidates:
            return None

        el = candidates[0]
        rect = el.BoundingRectangle
        if not rect or rect.width() <= 0 or rect.height() <= 0:
            return None
        # BoundingRectangle: left, top, right, bottom (логические пиксели экрана).
        x = rect.left
        y = rect.top
        w = rect.width()
        h = rect.height()
        # Если окно не на активном мониторе — можно сопоставить через display_calibration.
        from uni.tools.display_calibration import to_physical, to_logical, load_profile
        prof = load_profile()
        # vision возвращает логические — оставляем как есть (UIA уже логические).
        return {
            "x": float(x), "y": float(y),
            "width": float(w), "height": float(h),
            "confidence": 0.75,  # UIA — детерминированный поиск, не VLM-уверенность
            "source": "uia",
        }
    except Exception as exc:
        logger.debug("uia_find_element упал: %s", exc)
        return None


def uia_describe() -> str | None:
    """Краткое описание активного окна/элемента через UIA (fallback analyze_desktop)."""
    uia = _import_uiautomation()
    if uia is None:
        return None
    try:
        fg = uia.GetForegroundControl()
        if fg is None:
            return None
        name = getattr(fg, "Name", "") or ""
        ctrl_type = getattr(fg, "ControlTypeName", "") or ""
        rect = fg.BoundingRectangle
        size = f" ({rect.width()}x{rect.height()})" if rect else ""
        return f"Активное окно: {name} [{ctrl_type}]{size}".strip()
    except Exception as exc:
        logger.debug("uia_describe упал: %s", exc)
        return None


def ocr_available() -> bool:
    """Доступен ли локальный OCR (pytesseract/easyocr)."""
    try:
        import pytesseract  # type: ignore  # noqa: F401
        return True
    except Exception:
        pass
    try:
        import easyocr  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False
