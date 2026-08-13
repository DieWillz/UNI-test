"""🤖 Замкнутый цикл «вижу → решаю → кликаю → проверяю взглядом».

Слой оркестрации между существующими capability (vision + computer).
НЕ является capability и НЕ импортирует capability напрямую — получает
готовые инстансы vision/computer через конструктор (соблюдаем правило
«capability не импортирует другой capability»).

Идея: найти элемент по описанию через vision.find_desktop_element (VLM
возвращает x,y,width,height,confidence в пикселях экрана), кликнуть по
центру через computer.click_human (человеко-подобно), затем проверить
результат повторным analyze_desktop. Цикл повторяется до max_steps.
Fail-closed: при низкой уверенности не кликаем, возвращаем clarify.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from uni.contracts import ToolResult


# Запрещённые подстроки в цели — защита от опасных системных действий.
# Fail-closed: любое совпадение -> статус "blocked", клик не производится.
_BLACKLIST = (
    "format ", "del ", "rm ", "rmdir", "reg delete", "shutdown",
    "powershell", "taskkill", "diskpart", "mkfs", "bcdedit",
    "cmd /c", "cmd.exe", "sc stop", "net stop", "net user",
    "schtasks", "wmic", "certutil", "fsutil", "takeown",
    "icacls", "attrib", "format", "mount ", "umount",
    "kill ", "pkill", "halt", "reboot", "logoff",
    "disable ", "uninstall", "remove-user", "reset-password",
)


class VisualActionAgent:
    """Bounded observe-locate-act-verify agent для управления ПК под зрением."""

    def __init__(
        self,
        computer,
        vision,
        *,
        max_steps: int = 8,
        confidence_threshold: float = 0.55,
        verify_delay: float = 1.2,
        safe_margin: int = 40,
        log: Callable[[str, object], None] | None = None,
    ) -> None:
        # computer/vision — инстансы capability, переданные извне.
        self._computer = computer
        self._vision = vision
        self.max_steps = max_steps
        self.confidence_threshold = confidence_threshold
        self.verify_delay = verify_delay
        # 🤖 отступ безопасности от краёв экрана (px): не кликаем в системные
        # зоны (верхняя/нижняя панель задач, углы уведомлений Windows).
        self.safe_margin = max(0, int(safe_margin))
        self.log = log or (lambda _event, _message: None)
        self.steps_used = 0
        self._stop = False  # 🤖 флаг экстренной остановки (СТОП из UI/voice)
        # 🤖 читаемая история шагов цикла для UI (увидела→сделала→увидела после)
        self.history: list[str] = []

    def request_stop(self) -> None:
        """Экстренно прервать текущий цикл (СТОП из UI/голоса)."""
        self._stop = True

    def reset(self) -> None:
        self._stop = False
        self.steps_used = 0
        self.history = []

    def status(self) -> dict:
        """Текущее состояние цикла для опроса UI (без выполнения)."""
        return {
            "active": self.steps_used > 0 and not self._stop,
            "steps": self.steps_used,
            "stopped": self._stop,
            "max_steps": self.max_steps,
            "history": list(self.history),
        }

    def get_history(self) -> list[str]:
        """Читаемая история шагов цикла (увидела→сделала→увидела после)."""
        return list(self.history)

    # -- публичный API ----------------------------------------------------
    async def act_on_screen(
        self,
        goal: str,
        max_steps: int | None = None,
        screen_size: tuple[int, int] | None = None,
    ) -> dict:
        """Замкнутый цикл: найти → кликнуть → проверить.

        Args:
            goal: цель естественным языком.
            max_steps: лимит итераций.
            screen_size: (width, height) экрана для защиты системных зон
                (не кликать в отступ safe_margin от краёв). Если None — проверка
                зоны не выполняется (безопасно по умолчанию).

        Возвращает dict:
            {"status": "success"|"failed"|"interrupted"|"clarify"|"blocked",
             "steps": [...], "error": str|None}
        """
        goal = (goal or "").strip()
        if not goal:
            return {"status": "clarify", "steps": [], "error": "Пустая цель"}
        low = goal.lower()
        if any(bad in low for bad in _BLACKLIST):
            return {
                "status": "blocked",
                "steps": [],
                "error": "Цель содержит запрещённую системную команду",
            }

        max_steps = max_steps or self.max_steps
        steps: list[dict[str, Any]] = []

        for step in range(1, max_steps + 1):
            self.steps_used = step
            if self._stop:  # 🤖 экстренная остановка
                self._stop = False
                return {"status": "interrupted", "steps": steps, "error": "Остановлено по команде СТОП"}
            # 1) ВИЖУ: ищем элемент на рабочем столе по описанию из цели
            located = await self._locate(goal)
            if located is None:
                # элемент совсем не найден — повторная попытка с переформулировкой
                steps.append({"step": step, "action": "locate", "result": "not_found"})
                self.history.append(f"шаг {step}: вижу — элемент «{goal}» не найден, пробую иначе")
                continue
            if located == "low_conf":
                # найден, но уверенность ниже порога — не кликаем (fail-closed)
                self.history.append(f"шаг {step}: вижу — найдено, но уверенность низкая, не кликаю")
                return {
                    "status": "clarify",
                    "steps": steps,
                    "error": "Низкая уверенность локации элемента",
                }

            element = located
            conf = float(element.get("confidence", 0.0))
            # 2) РЕШАЮ + ДЕЙСТВУЮ: клик по центру найденного элемента
            cx = int(element["x"] + element["width"] / 2)
            cy = int(element["y"] + element["height"] / 2)
            # 🤖 защита системных зон: не кликаем в отступе safe_margin от краёв
            if screen_size is not None:
                sw, sh = screen_size
                m = self.safe_margin
                if not (m <= cx <= sw - m and m <= cy <= sh - m):
                    steps.append({
                        "step": step, "action": "click",
                        "x": cx, "y": cy, "success": False,
                        "message": f"цель в системной зоне (отступ {m}px) — клик заблокирован",
                    })
                    return {
                        "status": "blocked",
                        "steps": steps,
                        "error": f"Координаты ({cx},{cy}) в системной зоне экрана",
                    }
            click = await self._click(cx, cy)
            steps.append({
                "step": step,
                "action": "click",
                "x": cx,
                "y": cy,
                "success": click.success,
                "message": click.message,
            })
            self.history.append(f"шаг {step}: сделала — клик по ({cx},{cy})")
            if not click.success:
                self.history.append(f"шаг {step}: клик не удался — {click.message}")
                continue

            # 3) ПРОВЕРЯЮ: достигнута ли цель (повторный анализ экрана)
            await asyncio.sleep(self.verify_delay)
            ok = await self._verify(goal)
            steps.append({"step": step, "action": "verify", "achieved": ok})
            if ok:
                self.history.append(f"шаг {step}: проверила — цель «{goal}» достигнута ✅")
                # 🤖 сохраняем успешную траекторию (B-05) — аддитивно, тихо
                try:
                    from uni.tools.trajectory_store import save_trajectory
                    save_trajectory(goal, steps, list(self.history), status="success")
                except Exception:
                    pass
                return {"status": "success", "steps": steps, "error": None}
            self.history.append(f"шаг {step}: проверила — пока не достигнуто, повторяю")

        return {
            "status": "failed",
            "steps": steps,
            "error": f"Цель не достигнута за {max_steps} шагов",
        }

    async def observe_text(self, goal: str) -> dict:
        """Только проверка/анализ без кликов — безопасный режим."""
        analysis = await self._vision.analyze_desktop(
            f"{goal}. Кратко ответь по-русски, фактически."
        )
        return {
            "status": "success" if analysis.success else "failed",
            "steps": [{"action": "observe", "message": analysis.message}],
            "error": None if analysis.success else analysis.message,
        }

    # -- внутреннее -------------------------------------------------------
    async def _locate(self, goal: str):
        self.log("GUI_LOCATE", goal)
        # Несколько формулировок, чтобы VLM надёжнее находил элемент.
        queries = [
            f"кнопка или поле для цели: {goal}",
            f"элемент интерфейса: {goal}",
            goal,
        ]
        # P1 FIX (FIX-AUDIT): реальный перебор формулировок. Возвращаем
        # "low_conf" ТОЛЬКО если ВСЕ формулировки нашли элемент, но ни одна
        # не дала уверенность >= порога. Если хоть одна дала уверенный
        # результат — возвращаем его. Если ни одна не нашла — None.
        # P2 FIX (FIX-AUDIT): vision.py возвращает success=False + data при
        # низком conf (не решает за оркестратора). Здесь любой найденный
        # элемент с conf < порога (неважно success True/False) -> low_conf_found.
        from uni.capabilities.vision import VISION_CONFIDENCE_THRESHOLD
        low_conf_found = False
        for q in queries:
            res = await self._vision.find_desktop_element(q)
            if res.success and res.data:
                data = dict(res.data)
                conf = data.get("confidence", 0.0)
                if conf >= VISION_CONFIDENCE_THRESHOLD:
                    return data
                # найдено, но уверенность низкая — запоминаем и пробуем
                # следующую формулировку (не возвращаем сразу!)
                low_conf_found = True
            elif (not res.success) and res.data:
                # P2: vision нашла, но conf < порога -> тоже low_conf
                low_conf_found = True
        # перебрали все формулировки:
        if low_conf_found:
            return "low_conf"   # нашли, но ни одна не уверенна
        return None             # ни одна формулировка не нашла элемент

    async def _click(self, x: int, y: int) -> ToolResult:
        self.log("GUI_CLICK", f"{x},{y}")
        # Человеко-подобный клик, fallback на обычный при недоступности движка.
        if getattr(self._computer, "use_human_motion", False):
            return await self._computer.click_human(x, y)
        return await self._computer.click(x, y)

    async def _verify(self, goal: str) -> bool:
        self.log("GUI_VERIFY", goal)
        # 🤖 V-03 (2026-08-13): Tier-1 verify — повторный поиск Tier-0 (UIA/OCR)
        # через verify_delay + дифф региона скрина. Если Tier-0 находит цель
        # повторно — считаем достигнутым (быстрый, без VLM). Иначе — VLM-проверка.
        try:
            from uni.tools.local_vision_fallback import find_desktop_element_tier0
            repeat = find_desktop_element_tier0(goal)
            if repeat:
                self.history.append(f"проверила (Tier-1 UIA/OCR повтор) — цель «{goal}» видна повторно ✅")
                return True
        except Exception as exc:
            self.log("GUI_VERIFY_TIER1", f"tier0 недоступен: {exc}")
        # VLM-проверка как fallback (как раньше)
        res = await self._vision.analyze_desktop(
            f"Цель была: «{goal}». Достигнут ли результат на экране? "
            f"Ответь только «да» или «нет», затем краткое пояснение."
        )
        if not res.success:
            return False
        text = (res.data or {}).get("analysis", res.message or "")
        return bool(re.search(r"\bда\b", text.lower()))
