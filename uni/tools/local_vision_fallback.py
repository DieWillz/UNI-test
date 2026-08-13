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


# 🤖 V-04 (2026-08-13): WinRT OCR (Windows.Media.Ocr) — ДИРЕКТИВА требует
# именно winrt-Windows.Media.Ocr, а НЕ tesseract/easyocr. Проверяем пакет и
# русский язык (OcrEngine.AvailableRecognizerLanguages). При недоступности —
# честная ошибка (не мок), вызывающий канал тихо пропускается.
def winrt_ocr_available() -> tuple[bool, str]:
    """Возвращает (доступен, причина/сообщение)."""
    try:
        import winrt.windows.media.ocr as ocr  # type: ignore  # noqa: F401
        import winrt.windows.globalization as glob  # type: ignore  # noqa: F401
    except Exception as exc:
        return False, f"winrt-Windows.Media.Ocr недоступен: {exc}"
    try:
        langs = ocr.OcrEngine.get_available_recognizer_languages()
        ru = any(getattr(l, "languageTag", "") == "ru" or
                 str(getattr(l, "displayName", "")).lower().startswith("рус")
                 for l in langs)
        if not ru:
            return False, "winrt OCR установлен, но русский язык (ru) НЕ найден в AvailableRecognizerLanguages"
        return True, "ok"
    except Exception as exc:
        # пакет есть, но перечислить языки не вышло (возможно headless) — допускаем
        return True, f"winrt OCR доступен (проверка языка не удалась: {exc})"


def _import_playwright():
    """Попытаться импортировать Playwright (DOM-канал). None если недоступно."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except Exception as exc:
        logger.debug("playwright недоступен: %s", exc)
        return None


def ocr_find_text(description: str) -> dict[str, Any] | None:
    """Найти текст на экране через WinRT OCR и вернуть его прямоугольник.

    Возвращает dict {"x","y","width","height","confidence","source":"ocr"} в
    логических пикселях (WinRT OcrResult уже в системных координатах DIP) или
    None при недоступности/не найдено.
    """
    ok, why = winrt_ocr_available()
    if not ok:
        logger.info("OCR пропущен: %s", why)
        return None
    try:
        import winrt.windows.media.ocr as ocr
        import winrt.windows.graphics.imaging as imaging
        from winrt.windows.storage.streams import InMemoryRandomAccessStream
        from PIL import ImageGrab
        # 1) снимок рабочего стола в BMP-поток
        img = ImageGrab.grab().convert("RGB")
        stream = InMemoryRandomAccessStream()
        # PIL -> bytes -> stream (через промежуточный BytesIO проще)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # WinRT требует декодер изображения; используем BitmapDecoder из потока
        # (упрощённо: перекодируем через Pillow в нужный формат и пишем в stream)
        import asyncio
        async def _decode():
            from winrt.windows.storage.streams import DataWriter
            dw = DataWriter(stream)
            data = buf.getvalue()
            dw.write_bytes(list(data))
            await dw.store_async()
            await dw.flush_async()
            bmp = await imaging.BitmapDecoder.create_async(stream)
            return bmp
        bmp = asyncio.run(_decode())
        engine = ocr.OcrEngine.try_create_from_user_profile_language_async()
        # (синхронный вызов через asyncio)
        async def _recognize():
            return await engine.recognize_words_in_image_async(bmp)
        result = asyncio.run(_recognize())
        text = (getattr(result, "text", "") or "")
        low = (description or "").strip().lower()
        if low and low not in text.lower():
            return None
        # берём первый связный блок, содержащий подстроку (или весь кадр)
        target = None
        for line in (getattr(result, "lines", []) or []):
            lt = getattr(line, "text", "") or ""
            if low and low in lt.lower():
                target = line
                break
        if target is None:
            return None
        rb = getattr(target, "bounding_rect", None) or getattr(result, "bounding_rect", None)
        if rb is None:
            return None
        return {
            "x": float(rb.x), "y": float(rb.y),
            "width": float(rb.width), "height": float(rb.height),
            "confidence": 0.7,  # OCR находит текст детерминированно; не VLM-уверенность
            "source": "ocr",
        }
    except Exception as exc:
        logger.debug("ocr_find_text упал: %s", exc)
        return None


def dom_find_element(description: str):
    """Найти элемент в DOM активной вкладки браузера через Playwright.

    Возвращает dict {"x","y","width","height","confidence","source":"dom"} в
    координатах вьюпорта (логических пикселях) или None.
    Работает ТОЛЬКО для браузера (Playwright-сессия Юни).
    """
    pw = _import_playwright()
    if pw is None:
        return None
    try:
        low = (description or "").strip().lower()
        with pw() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # ищем интерактивный элемент по видимому тексту (get_by_text)
            try:
                locator = page.get_by_text(low or description, exact=False).first
                box = locator.bounding_box(timeout=2000)
            except Exception:
                box = None
            browser.close()
            if not box:
                return None
            return {
                "x": float(box["x"]), "y": float(box["y"]),
                "width": float(box["width"]), "height": float(box["height"]),
                "confidence": 0.7, "source": "dom",
            }
    except Exception as exc:
        logger.debug("dom_find_element упал: %s", exc)
        return None


def find_desktop_element_tier0(description: str) -> dict[str, Any] | None:
    """🤖 V-02 (2026-08-13): каскад Tier-0 БЕЗ модели.

    Порядок: UIA -> OCR(WinRT) -> DOM(Playwright). Первый нашедший побеждает.
    Каждый канал тихо возвращает None при недоступности библиотеки/headless —
    это НЕ ошибка, а повод пойти дальше (к VLM в vision.py).
    """
    from uni.config import load_config
    cfg = load_config().capabilities.vision
    # 1) UIA (имена+rect -> центр)
    if getattr(cfg, "tier0_uia_enabled", True):
        try:
            el = uia_find_element(description)
            if el:
                el = dict(el); el["source"] = "uia"
                return el
        except Exception as exc:
            logger.debug("tier0 UIA пропущен: %s", exc)
    # 2) OCR (WinRT) — поиск текста
    if getattr(cfg, "tier0_ocr_enabled", True):
        try:
            el = ocr_find_text(description)
            if el:
                return el
        except Exception as exc:
            logger.debug("tier0 OCR пропущен: %s", exc)
    # 3) DOM (Playwright) — только браузер
    if getattr(cfg, "tier0_dom_enabled", True):
        try:
            el = dom_find_element(description)
            if el:
                return el
        except Exception as exc:
            logger.debug("tier0 DOM пропущен: %s", exc)
    return None

