from __future__ import annotations

import re
from typing import Any

from uni.browser_session import BrowserSession
from uni.contracts import ToolResult
from .base import Capability


class XToysCapability(Capability):
    """Best-effort XToys UI adapter over the shared persistent browser session."""

    name = "xtoys"
    description = "Управление активной вкладкой XToys.app"

    def __init__(self, session: BrowserSession, *, url: str, max_intensity: int = 50):
        self.session = session
        self.url = url
        self.max_intensity = max(0, min(100, max_intensity))

    async def _page(self):
        return await self.session.page_for_host("xtoys.app", create_url=self.url)

    async def open(self) -> ToolResult:
        try:
            page = await self._page()
            return ToolResult(
                success=True,
                data={"url": page.url, "title": await page.title()},
                message="Вкладка XToys.app открыта и выбрана",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Не удалось открыть XToys.app: {exc}")

    @staticmethod
    def _vertical_slider_point(box: dict[str, float], value: int) -> tuple[float, float]:
        bounded = max(0, min(int(value), 100))
        inset = min(3.0, float(box["height"]) / 10)
        x = float(box["x"]) + float(box["width"]) / 2
        y = float(box["y"]) + inset + (float(box["height"]) - 2 * inset) * (1 - bounded / 100)
        return x, y

    async def _set_custom_speed(self, page, requested: int, device: str) -> dict[str, Any]:
        candidates = page.locator('div[tabindex="0"].cursor-pointer')
        selected = None
        selected_text = ""
        needle = device.casefold().strip()
        for index in range(min(await candidates.count(), 100)):
            candidate = candidates.nth(index)
            if not await candidate.is_visible():
                continue
            text = (await candidate.inner_text()).strip()
            if not re.search(r"(?:^|\s)(?:speed|intensity|скорость|интенсивность)(?:\s|$)", text, re.I):
                continue
            if needle and needle != "default":
                parent_text = await candidate.evaluate(
                    "el => (el.parentElement?.parentElement?.innerText || '').slice(0, 2000)"
                )
                if needle not in parent_text.casefold():
                    continue
            selected = candidate
            selected_text = text
            break
        if selected is None:
            return {"ok": False, "reason": "Не найден видимый вертикальный контрол Speed"}
        box = await selected.bounding_box()
        if not box or float(box["height"]) < 40 or float(box["height"]) <= float(box["width"]):
            return {"ok": False, "reason": "Контрол Speed имеет небезопасную геометрию"}
        x, y = self._vertical_slider_point(box, requested)
        await page.mouse.move(x, y, steps=12)
        await page.mouse.click(x, y)
        await page.wait_for_timeout(500)
        updated_text = (await selected.inner_text()).strip()
        values = [int(value) for value in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", updated_text)]
        displayed = values[-1] if values else None
        verified_ui = displayed is not None and abs(displayed - requested) <= 1
        return {
            "ok": verified_ui,
            "reason": None if verified_ui else f"После клика Speed показывает {displayed!r}, ожидалось {requested}",
            "control": "custom_vertical_speed",
            "before_text": selected_text[:200],
            "displayed_value": displayed,
            "requested_value": requested,
            "verified_ui": verified_ui,
        }

    async def set_intensity(self, device: str = "", value: int = 0) -> ToolResult:
        requested = max(0, min(100, int(value)))
        if requested > self.max_intensity:
            return ToolResult(
                success=False,
                message=(
                    f"Запрошено {requested}%, но защитный максимум UNI — "
                    f"{self.max_intensity}%. Измените capabilities.xtoys.max_intensity в config.yaml осознанно."
                ),
            )
        try:
            page = await self._page()
            result: dict[str, Any] = await page.evaluate(
                """({device, value}) => {
                    const visible = el => {
                        const s = getComputedStyle(el);
                        const r = el.getBoundingClientRect();
                        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                    };
                    const ranges = [...document.querySelectorAll('input[type="range"]')].filter(visible);
                    if (!ranges.length) return {ok: false, reason: 'На странице нет видимого input[type=range]'};
                    const needle = (device || '').trim().toLowerCase();
                    let target = ranges[0];
                    if (needle) {
                        target = ranges.find(el => {
                            let node = el;
                            for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
                                if ((node.innerText || '').toLowerCase().includes(needle)) return true;
                            }
                            return false;
                        }) || target;
                    }
                    const min = Number(target.min || 0);
                    const max = Number(target.max || 100);
                    const normalized = min + (max - min) * (value / 100);
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    setter.call(target, String(normalized));
                    target.dispatchEvent(new Event('input', {bubbles: true}));
                    target.dispatchEvent(new Event('change', {bubbles: true}));
                    const displayed = Math.round(((Number(target.value) - min) / (max - min || 1)) * 100);
                    return {
                        ok: displayed === value,
                        reason: displayed === value ? null : `После изменения input показывает ${displayed}`,
                        control: 'input_range',
                        displayed_value: displayed,
                        verified_ui: displayed === value,
                        value,
                        min,
                        max
                    };
                }""",
                {"device": device, "value": requested},
            )
            if not result.get("ok"):
                result = await self._set_custom_speed(page, requested, device)
            if not result.get("ok"):
                return ToolResult(success=False, message=f"Слайдер XToys не изменён: {result.get('reason')}")
            return ToolResult(
                success=True,
                data={
                    "requested_percent": requested,
                    "device": device or None,
                    "control": result.get("control", "input_range"),
                    "displayed_value": result.get("displayed_value"),
                    "verified_ui": bool(result.get("verified_ui", result.get("ok"))),
                    "verified_physical": False,
                },
                message=(
                    f"Интерфейс XToys показывает интенсивность {requested}%; "
                    "физическая реакция устройства не подтверждена"
                ),
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка XToys intensity: {exc}")

    async def toggle(self, device: str = "") -> ToolResult:
        try:
            page = await self._page()
            buttons = page.get_by_role("button")
            candidates: list[tuple[int, Any, str]] = []
            needle = device.strip().lower()
            tokens = ("connect", "disconnect", "start", "stop", "on", "off", "подключ", "включ", "выключ")
            for index in range(min(await buttons.count(), 80)):
                button = buttons.nth(index)
                if not await button.is_visible():
                    continue
                text = (await button.inner_text()).strip()
                lowered = text.lower()
                score = 2 if any(token in lowered for token in tokens) else 0
                if needle:
                    parent_text = await button.evaluate("el => (el.parentElement?.innerText || '').slice(0, 1000)")
                    if needle in parent_text.lower():
                        score += 3
                if score:
                    candidates.append((score, button, text))
            if not candidates:
                return ToolResult(success=False, message="Не найдена кнопка подключения/включения XToys")
            _, button, label = max(candidates, key=lambda item: item[0])
            await button.click(timeout=10_000)
            return ToolResult(
                success=True,
                data={"button": label, "device": device or None, "verified": False},
                message=f"В XToys нажата кнопка «{label or 'без названия'}»; итоговое состояние не подтверждено",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка XToys toggle: {exc}")

    async def select_pattern(self, pattern: str, device: str = "") -> ToolResult:
        if not pattern.strip():
            return ToolResult(success=False, message="Название паттерна не указано")
        try:
            page = await self._page()
            selectors = page.get_by_text(pattern.strip(), exact=False)
            if await selectors.count() == 0:
                openers = page.get_by_text("Pattern", exact=False)
                if await openers.count() == 0:
                    openers = page.get_by_text("No Pattern", exact=False)
                if await openers.count():
                    await openers.first.click(timeout=10_000)
                    await page.wait_for_timeout(500)
                selectors = page.get_by_text(pattern.strip(), exact=False)
            visible = None
            for index in range(min(await selectors.count(), 50)):
                item = selectors.nth(index)
                if await item.is_visible():
                    visible = item
                    break
            if visible is None:
                return ToolResult(success=False, message=f"Паттерн «{pattern}» не найден в XToys")
            await visible.click(timeout=10_000)
            return ToolResult(
                success=True,
                data={"pattern": pattern, "device": device or None, "verified": False},
                message=f"Выбор паттерна «{pattern}» отправлен в XToys; состояние устройства не подтверждено",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка выбора паттерна XToys: {exc}")

    async def get_status(self, device: str = "") -> ToolResult:
        try:
            page = await self._page()
            text = (await page.locator("body").inner_text(timeout=10_000)).strip()
            if device:
                lines = [line for line in text.splitlines() if device.lower() in line.lower()]
                summary = "\n".join(lines[:20]) or text[:3000]
            else:
                summary = text[:3000]
            return ToolResult(
                success=True,
                data={"url": page.url, "visible_text": summary, "verified": False},
                message="Получено видимое состояние вкладки XToys",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения XToys: {exc}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        device = str(kwargs.get("device", ""))
        if action == "open":
            return await self.open()
        if action == "toggle":
            return await self.toggle(device)
        if action == "set_intensity":
            return await self.set_intensity(device, int(kwargs.get("value", 0)))
        if action == "select_pattern":
            return await self.select_pattern(str(kwargs.get("pattern", "")), device)
        if action == "get_status":
            return await self.get_status(device)
        return ToolResult(success=False, message=f"Неизвестное действие xtoys.{action}")
