from __future__ import annotations

import asyncio
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
        self.verified_physical = False

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

    _FIND_SPEED_JS = """({device}) => {
        const needle = (device || '').trim().toLowerCase();
        const textOf = el => (el.innerText || '');
        const visible = el => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0 && el.offsetParent !== null;
        };
        const els = [...document.querySelectorAll('div, section, [role="slider"]')].filter(el => {
            const t = textOf(el);
            if (!/speed|intensity|скорость|интенсивность/i.test(t)) return false;
            const r = el.getBoundingClientRect();
            if (r.width < 20 || r.height < 40) return false;
            if (!visible(el)) return false;
            if (needle && needle !== 'default' && !t.toLowerCase().includes(needle)) return false;
            return true;
        });
        if (!els.length) return {ok: false, reason: 'Не найден контрол Speed'};
        els.sort((a, b) => {
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return (rb.height * rb.width) - (ra.height * ra.width);
        });
        const el = els[0];
        const r = el.getBoundingClientRect();
        const nums = (textOf(el).match(/(?<!\\d)(\\d{1,3})(?!\\d)/g) || []).map(Number);
        const displayed = nums.length ? nums[nums.length - 1] : null;
        return {ok: true, rect: {x: r.x, y: r.y, w: r.width, h: r.height}, displayed};
    }"""

    async def _find_speed(self, page, device: str) -> dict[str, Any]:
        try:
            return await page.evaluate(self._FIND_SPEED_JS, {"device": device})
        except Exception as exc:
            return {"ok": False, "reason": f"Ошибка поиска Speed: {exc}"}

    async def _set_custom_speed(self, page, requested: int, device: str) -> dict[str, Any]:
        """Set the XToys Speed control by clicking the panel at the value's height.

        Works for BOTH a thin vertical slider AND a wide Speed panel (e.g. the
        Fredorch Rotary block on xtoys.app, which is ~1164x655). Mapping: top of
        the control = 100%, bottom = 0%. We pick the largest on-page block whose
        text mentions Speed/Скорость, click at the right Y and read the displayed
        number back to verify. The old geometry guard (height <= width) is gone —
        a wide panel is a perfectly valid control.
        """
        info = await self._find_speed(page, device)
        if not info.get("ok"):
            return {"ok": False, "reason": info.get("reason", "Не найден контрол Speed")}
        rect = info["rect"]
        top_inset = max(6.0, rect["h"] * 0.10)
        bot_inset = max(6.0, rect["h"] * 0.04)
        usable = max(1.0, rect["h"] - top_inset - bot_inset)
        bounded = max(0, min(100, int(requested)))
        y = rect["y"] + top_inset + usable * (1 - bounded / 100.0)
        x = rect["x"] + rect["w"] / 2.0
        await page.mouse.move(x, y, steps=12)
        await page.mouse.click(x, y)
        await page.wait_for_timeout(500)
        after = await self._find_speed(page, device)
        displayed = after.get("displayed") if after.get("ok") else None
        verified_ui = displayed is not None and abs(int(displayed) - int(requested)) <= 2
        return {
            "ok": verified_ui,
            "reason": None if verified_ui else f"Speed показывает {displayed!r}, ожидалось {requested}",
            "control": "custom_speed_panel",
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

    async def read_intensity(self, device: str = "") -> ToolResult:
        """Read the current slider value back from the live DOM (verification)."""
        try:
            page = await self._page()
            result = await page.evaluate(
                """({device}) => {
                    const visible = el => {
                        const s = getComputedStyle(el);
                        const r = el.getBoundingClientRect();
                        return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                    };
                    const ranges = [...document.querySelectorAll('input[type="range"]')].filter(visible);
                    if (!ranges.length) return {ok: false, reason: 'Нет видимого input[type=range]'};
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
                    const displayed = Math.round(((Number(target.value) - min) / (max - min || 1)) * 100);
                    return {ok: true, value: displayed};
                }""",
                {"device": device},
            )
            if not result.get("ok"):
                return ToolResult(success=False, message=str(result.get("reason", "Не удалось прочитать слайдер")))
            return ToolResult(
                success=True,
                data={"value": int(result["value"]), "device": device or None},
                message=f"Текущая интенсивность XToys: {result['value']}%",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения XToys: {exc}")

    async def ramp_intensity(self, device: str = "", target: int = 0, *, steps: int = 5) -> ToolResult:
        """Safely ramp intensity toward `target` in small increments (no sudden jumps)."""
        target = max(0, min(100, int(target)))
        try:
            current = 0
            read = await self.read_intensity(device)
            if read.success and isinstance(read.data, dict):
                current = int(read.data.get("value", 0))
        except Exception:
            current = 0
        if current == target:
            return await self.set_intensity(device, target)
        steps = max(1, min(steps, 20))
        lo, hi = (current, target) if target > current else (target, current)
        span = hi - lo
        sequence = [lo + round(span * (i + 1) / steps) for i in range(steps)]
        if target < current:
            sequence = sequence[::-1]
        last: ToolResult | None = None
        for value in sequence:
            last = await self.set_intensity(device, value)
            if not (last and last.success):
                return last or ToolResult(success=False, message="Прервано на шаге ramp")
            await asyncio.sleep(0.4)
        return last or await self.set_intensity(device, target)

    async def set_verified_physical(self, verified: bool = True) -> ToolResult:
        """Explicit, intentional acknowledgment that the physical device is engaged.

        By default the device is NEVER activated: callers in autonomous mode must
        opt in via config (capabilities.xtoys.autonomous_physical) before this is
        allowed to return success. This preserves the safety contract.
        """
        self.verified_physical = bool(verified)
        return ToolResult(
            success=True,
            data={"verified_physical": self.verified_physical},
            message=(
                "Физическое подтверждение устройства принято"
                if self.verified_physical
                else "Физическое подтверждение снято"
            ),
        )

    async def execute(self, action: str, **kwargs) -> ToolResult:
        device = str(kwargs.get("device", ""))
        if action == "open":
            return await self.open()
        if action == "toggle":
            return await self.toggle(device)
        if action == "set_intensity":
            return await self.set_intensity(device, int(kwargs.get("value", 0)))
        if action == "ramp_intensity":
            return await self.ramp_intensity(device, int(kwargs.get("value", 0)), steps=int(kwargs.get("steps", 5)))
        if action == "read_intensity":
            return await self.read_intensity(device)
        if action == "set_verified_physical":
            return await self.set_verified_physical(bool(kwargs.get("verified", True)))
        if action == "select_pattern":
            return await self.select_pattern(str(kwargs.get("pattern", "")), device)
        if action == "get_status":
            return await self.get_status(device)
        return ToolResult(success=False, message=f"Неизвестное действие xtoys.{action}")
