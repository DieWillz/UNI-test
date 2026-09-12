import asyncio
import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import comtypes.client
import pyautogui
import win32clipboard
import win32con
import win32gui
import win32api
import win32process
from comtypes.gen import UIAutomationClient as uia
from uni.contracts import ToolResult
from uni.utils.file_lock import acquire_lock, release_lock
from .base import Capability

# 🤖 Человеко-подобная мышь (win32api, траектории): отдельный движок рядом
# с pyautogui. Импорт ленивый/защищённый — если модуль недоступен (headless),
# capability продолжает работать на pyautogui-fallback.
try:
    from .human_mouse import HumanMouseController, HumanMouseSettings
except Exception:  # pragma: no cover - защита от отсутствия win32api в CI
    HumanMouseController = None
    HumanMouseSettings = None

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

class ComputerCapability(Capability):
    name = "computer"
    description = "Управление мышью, клавиатурой, приложениями"
    # 🤖 Безопасность (P0.11): чёрный список запускаемых приложений/команд
    BLACKLISTED_COMMANDS = (
        "format", "del", "rm", "regedit", "shutdown",
        "taskkill", "reboot", "poweroff", "erase", "rd", "rmdir",
    )

    def __init__(
        self,
        use_uia: bool = True,
        failsafe: bool = True,
        mouse_move_duration: float = 0.35,
        use_human_motion: bool = True,
        telegram_uni_path: str | Path | None = None,
        telegram_user_path: str | Path | None = None,
        action_badge_enabled: bool = True,
        action_badge_label: str = "UNI",
        verified_physical: bool = True,
    ):
        self.use_uia = use_uia
        self.mouse_move_duration = max(0.0, min(float(mouse_move_duration), 2.0))
        # 🤖 Человеко-подобный движок (win32api) — активен по умолчанию как
        # более реалистичный; pyautogui остаётся fallback через action="click".
        self.use_human_motion = bool(use_human_motion) and HumanMouseController is not None
        self._human_mouse = None
        if self.use_human_motion:
            try:
                self._human_mouse = HumanMouseController(
                    HumanMouseSettings(move_duration=self.mouse_move_duration)
                )
            except Exception:
                self.use_human_motion = False  # откат на pyautogui при сбое
                self._human_mouse = None
        # 🤖 Hermes (2026-08-14): режим мыши Юни — поля (аддитивно, не меняет
        # поведение старых action-веток). Методы set_mouse_mode/_browser_automation
        # добавлены как методы класса ниже (после __init__).
        self.mouse_mode = False
        self._browser_automation_cache = None

        project_root = Path(__file__).resolve().parents[2]

        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        self.telegram_uni_path = Path(telegram_uni_path or project_root / "Telegram" / "Telegram.exe")
        self.telegram_user_path = Path(
            telegram_user_path or appdata / "Telegram Desktop" / "Telegram.exe"
        )
        pyautogui.FAILSAFE = failsafe
        self._badge = None
        self.verified_physical = bool(verified_physical)

        if action_badge_enabled:
            try:
                from uni.action_badge import UniActionBadge

                self._badge = UniActionBadge(enabled=True, label=action_badge_label)
            except Exception:
                self._badge = None

    # 🤖 Hermes (2026-08-14): режим мыши Юни — методы класса (аддитивно).
    # Старые action-ветки execute (pyautogui/UIA) не тронуты; эти методы
    # используются только ветками open_browser/open_new_tab/type_url и
    # set_mouse_mode внутри execute().
    def set_mouse_mode(self, enabled: bool) -> None:
        """Включает/выключает визуально-управляемую мышь Юни."""
        self.mouse_mode = bool(enabled)

    def _browser_automation(self):
        """Ленивый доступ к BrowserAutomation (не тянет зависимости при import)."""
        if self._browser_automation_cache is None:
            from uni.mouse.browser_automation import BrowserAutomation
            self._browser_automation_cache = BrowserAutomation()
        return self._browser_automation_cache

    def _flash_badge(self, x: int, y: int, action: str = "click") -> None:
        if self._badge is not None:
            try:
                self._badge.flash_at(x, y, action)
            except Exception:
                pass

    def _require_physical(self) -> None:
        # 🤖 Безопасность (P0.12): gate для физических действий
        if not self.verified_physical:
            raise ValueError("Требуется подтверждение для физических действий (verified_physical=False)")

    def _check_command_allowed(self, app_name: str) -> None:
        # 🤖 Безопасность (P0.11): чёрный список
        low = (app_name or "").lower()

        for banned in self.BLACKLISTED_COMMANDS:
            if banned in low:
                raise ValueError(f"Запрещённая команда/приложение: {app_name!r} (содержит {banned!r})")

    @staticmethod
    def _activate_window(hwnd: int) -> None:
        foreground = win32gui.GetForegroundWindow()
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        foreground_thread = 0
        if foreground:
            foreground_thread, _ = win32process.GetWindowThreadProcessId(foreground)
        attached: list[int] = []
        activation_error: Exception | None = None
        try:
            for thread_id in {target_thread, foreground_thread}:
                if thread_id and thread_id != current_thread:
                    if ctypes.windll.user32.AttachThreadInput(current_thread, thread_id, True):
                        attached.append(thread_id)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.BringWindowToTop(hwnd)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as exc:
                activation_error = exc
                # Windows may reject SetForegroundWindow unless the caller has
                # just received input. A bounded Alt pulse is the documented
                # foreground-lock workaround used by desktop automation tools.
                ctypes.windll.user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
                try:
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except Exception as retry_exc:
                        activation_error = retry_exc
                finally:
                    ctypes.windll.user32.keybd_event(
                        win32con.VK_MENU,
                        0,
                        win32con.KEYEVENTF_KEYUP,
                        0,
                    )
            if win32gui.GetForegroundWindow() != hwnd:
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
                time.sleep(0.1)
            if win32gui.GetForegroundWindow() != hwnd:
                left, top, right, _bottom = win32gui.GetWindowRect(hwnd)
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
                )
                # Click only the top title strip, never application content.
                pyautogui.click(max(left + 80, (left + right) // 2), max(top + 8, 8))
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                )
                time.sleep(0.1)
            if win32gui.GetForegroundWindow() != hwnd:
                if activation_error is not None:
                    raise activation_error
                raise RuntimeError("Windows не перевела выбранное окно на передний план")
        finally:
            for thread_id in attached:
                ctypes.windll.user32.AttachThreadInput(current_thread, thread_id, False)

    async def launch_app(self, app_name: str) -> ToolResult:
        key = app_name.casefold().strip()
        lock_name = f"runtime/locks/launch_{key}"
        if not acquire_lock(lock_name):
            return ToolResult(success=False, message=f"Запуск «{app_name}» уже выполняется (lock)")
        try:
            if key in {"telegram", "телеграм"}:
                return ToolResult(
                    success=False,
                    message="Укажите telegram_uni или telegram_user; общий Telegram неоднозначен",
                )
            if key in {"telegram_user", "телеграм_пользователя"}:
                return ToolResult(
                    success=False,
                    message="Личный Telegram не запускается через UNI; используйте telegram_uni",
                )
            if key in {"telegram_uni", "телеграм_юни"}:
                if not self.telegram_uni_path.is_file():
                    return ToolResult(
                        success=False,
                        message=f"Telegram UNI не найден: {self.telegram_uni_path}",
                    )
                try:
                    await asyncio.to_thread(
                        subprocess.Popen,
                        [str(self.telegram_uni_path)],
                        cwd=str(self.telegram_uni_path.parent),
                    )
                    return ToolResult(success=True, message="Запущен отдельный Telegram UNI")
                except Exception as exc:
                    return ToolResult(success=False, message=f"Ошибка запуска Telegram UNI: {exc}")
            apps = {
                "notepad": "notepad.exe",
                "блокнот": "notepad.exe",
                "calc": "calc.exe",
                "калькулятор": "calc.exe",
                "explorer": "explorer.exe",
                "проводник": "explorer.exe",
                "chrome": "chrome.exe",
                "браузер": "chrome.exe",
            }
            cmd = apps.get(key, app_name)
            try:
                await asyncio.to_thread(subprocess.Popen, cmd)
                return ToolResult(success=True, message=f"Запущено: {app_name}")
            except Exception as e:
                return ToolResult(success=False, message=f"Ошибка: {e}")
        finally:
            # 🤖 FIX (Hermes, 2026-08-14): убран безусловный return из finally.
            # Старый код (DEPRECATED by Hermes):
            #     finally:
            #         release_lock(lock_name)
            #         return ToolResult(success=False, message=f"Ошибка: {e}")
            # Здесь `e` не определена в области finally (exception-переменная
            # живёт только внутри своего except) -> NameError и гашение
            # успешных return из try. Теперь finally только освобождает lock;
            # результат определяется return-ами из try/except.
            release_lock(lock_name)

    async def click(self, x: int, y: int, button: str = "left") -> ToolResult:
        self._require_physical()
        try:
            self._flash_badge(x, y, f"click:{button}")
            await asyncio.to_thread(
                pyautogui.moveTo,
                x,
                y,
                duration=self.mouse_move_duration,
            )
            await asyncio.to_thread(pyautogui.click, x, y, button=button)
            return ToolResult(success=True, message=f"Клик ({x},{y})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def move(self, x: int, y: int) -> ToolResult:
        """Переместить системный курсор без клика."""
        self._require_physical()
        try:
            await asyncio.to_thread(pyautogui.moveTo, x, y, duration=self.mouse_move_duration)
            return ToolResult(success=True, message=f"Курсор перемещён ({x},{y})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка перемещения: {e}")

    # 🤖 Человеко-подобные действия (win32api, реалистичные траектории).
    # Старый action="click" (pyautogui) сохранён как быстрый fallback.
    async def click_human(self, x: int, y: int, button: str = "left") -> ToolResult:
        self._require_physical()
        if self._human_mouse is None:
            return await self.click(x, y, button)  # graceful fallback
        try:
            await self._human_mouse.click(x, y, button)
            return ToolResult(success=True, message=f"Клик (человеко-подобный) ({x},{y})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def double_click_human(self, x: int, y: int, button: str = "left") -> ToolResult:
        self._require_physical()
        if self._human_mouse is None:
            return ToolResult(success=False, message="human_mouse недоступен")
        try:
            await self._human_mouse.double_click(x, y, button)
            return ToolResult(success=True, message=f"Двойной клик (человеко-подобный) ({x},{y})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def drag_human(self, x1: int, y1: int, x2: int, y2: int,
                          button: str = "left") -> ToolResult:
        self._require_physical()
        if self._human_mouse is None:
            return ToolResult(success=False, message="human_mouse недоступен")
        try:
            await self._human_mouse.drag(x1, y1, x2, y2, button)
            return ToolResult(success=True, message=f"Drag (человеко-подобный) ({x1},{y1})->({x2},{y2})")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def type_text(self, text: str, interval: float = 0.05) -> ToolResult:
        self._require_physical()
        try:
            await asyncio.to_thread(pyautogui.typewrite, text, interval=interval)
            return ToolResult(success=True, message=f"Напечатано: {text[:50]}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    @staticmethod
    def _post_unicode_to_foreground(text: str, interval: float = 0.01) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise ValueError("Нет активного окна")
        encoded = text.encode("utf-16-le")
        units = [int.from_bytes(encoded[index:index + 2], "little") for index in range(0, len(encoded), 2)]
        for unit in units:
            win32gui.PostMessage(hwnd, win32con.WM_CHAR, unit, 1)
            time.sleep(interval)

    async def type_unicode(self, text: str, interval: float = 0.01) -> ToolResult:
        self._require_physical()
        if not text:
            return ToolResult(success=False, message="Текст пуст")
        try:
            await asyncio.to_thread(self._post_unicode_to_foreground, text, interval)
            return ToolResult(success=True, message=f"Unicode-текст передан активному окну: {len(text)} символов")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка Unicode-ввода в активное окно: {exc}")

    @staticmethod
    def _post_hotkey_to_foreground(combo: str) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise ValueError("Нет активного окна")
        parts = [part.strip().casefold() for part in combo.split("+") if part.strip()]
        if not parts:
            raise ValueError("Комбинация клавиш пуста")
        modifier_map = {
            "ctrl": win32con.VK_CONTROL,
            "shift": win32con.VK_SHIFT,
            "alt": win32con.VK_MENU,
        }
        modifiers = [modifier_map[part] for part in parts[:-1] if part in modifier_map]
        key_name = parts[-1]
        named_keys = {
            "left": win32con.VK_LEFT,
            "right": win32con.VK_RIGHT,
            "home": win32con.VK_HOME,
            "end": win32con.VK_END,
            "backspace": win32con.VK_BACK,
        }
        if key_name in named_keys:
            key_code = named_keys[key_name]
        elif len(key_name) == 1:
            key_code = win32api.VkKeyScan(key_name) & 0xFF
        else:
            raise ValueError(f"Неподдерживаемая оконная клавиша: {key_name}")
        for modifier in modifiers:
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, modifier, 0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, key_code, 0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, key_code, 0)
        for modifier in reversed(modifiers):
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, modifier, 0)
        time.sleep(0.15)

    async def press_window_hotkey(self, key: str) -> ToolResult:
        try:
            await asyncio.to_thread(self._post_hotkey_to_foreground, key)
            return ToolResult(success=True, message=f"Оконная комбинация передана: {key}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка оконной комбинации: {exc}")

    @staticmethod
    def _delete_backward_in_foreground(count: int) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise ValueError("Нет активного окна")
        for _ in range(max(1, min(count, 2000))):
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_BACK, 0)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_BACK, 0)
        time.sleep(0.3)

    async def delete_backward(self, count: int = 1000) -> ToolResult:
        try:
            bounded = max(1, min(count, 2000))
            await asyncio.to_thread(self._delete_backward_in_foreground, bounded)
            return ToolResult(success=True, message=f"Передано удалений назад: {bounded}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка очистки активного поля: {exc}")

    @staticmethod
    def _paste_unicode(text: str) -> None:
        previous: str | None = None
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.6)
        finally:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                if previous is not None:
                    win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

    async def paste_text(self, text: str) -> ToolResult:
        if not text:
            return ToolResult(success=False, message="Текст пуст")
        try:
            await asyncio.to_thread(self._paste_unicode, text)
            return ToolResult(success=True, message="Unicode-текст вставлен")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка вставки: {exc}")

    @staticmethod
    def _copy_selected_text() -> str:
        previous: str | None = None
        sentinel = f"__UNI_COPY_SENTINEL_{time.time_ns()}__"
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(sentinel, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            ComputerCapability._post_hotkey_to_foreground("ctrl+c")
            time.sleep(0.4)
            win32clipboard.OpenClipboard()
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                raise ValueError("Выделенный текст не появился в буфере обмена")
            copied = str(win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT))
            if copied == sentinel:
                raise ValueError("Активное окно не скопировало выделенный текст")
            win32clipboard.EmptyClipboard()
            if previous is not None:
                win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return copied
        finally:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                if previous is not None:
                    win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

    async def copy_selected_text(self) -> ToolResult:
        try:
            value = await asyncio.to_thread(self._copy_selected_text)
            return ToolResult(success=True, data={"value": value}, message="Выделенный текст прочитан")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения выделенного текста: {exc}")

    @staticmethod
    def _focus_window(title_contains: str) -> tuple[bool, str]:
        needle = title_contains.casefold()
        matches: list[tuple[int, str]] = []

        def callback(hwnd, _extra):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if needle in title.casefold() and "мини-приложение" not in title.casefold():
                matches.append((hwnd, title))

        win32gui.EnumWindows(callback, None)
        if len(matches) != 1:
            return False, f"Ожидалось одно окно {title_contains!r}, найдено: {len(matches)}"
        hwnd, title = matches[0]
        ComputerCapability._activate_window(hwnd)
        return True, title

    async def focus_window(self, title_contains: str) -> ToolResult:
        try:
            success, detail = await asyncio.to_thread(self._focus_window, title_contains)
            return ToolResult(success=success, message=(f"Окно активно: {detail}" if success else detail))
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка фокуса окна: {exc}")

    @staticmethod
    def _normalize_executable_path(path: str | Path) -> str:
        return str(Path(path).resolve(strict=False)).replace("/", "\\").casefold()

    @staticmethod
    def _query_process_path(pid: int) -> str:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess failed")
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                raise OSError(ctypes.get_last_error(), "QueryFullProcessImageNameW failed")
            return buffer.value
        finally:
            kernel32.CloseHandle(handle)

    def _focus_app(self, app_name: str) -> tuple[bool, str]:
        key = app_name.casefold().strip()
        # The planner sees executable names in list_visible_windows(). Accept
        # those exact names as aliases; keep ambiguous-window rejection intact.
        key = {"chrome.exe": "chrome", "msedge.exe": "edge",
               "browser.exe": "yandex", "telegram.exe": "telegram"}.get(key, key)
        matches: list[tuple[int, str]] = []
        telegram_keys = {
            "telegram",
            "телеграм",
            "telegram_uni",
            "телеграм_юни",
            "telegram_user",
            "телеграм_пользователя",
        }
        uni_path = self._normalize_executable_path(self.telegram_uni_path)
        user_path = self._normalize_executable_path(self.telegram_user_path)

        def callback(hwnd, _extra):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            is_telegram = False
            if (
                key in telegram_keys
                and class_name.startswith("Qt515")
                and class_name.endswith("QWindowIcon")
                and "мини-приложение" not in title.casefold()
            ):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    executable_path = self._normalize_executable_path(self._query_process_path(pid))
                    if key in {"telegram", "телеграм"}:
                        is_telegram = Path(executable_path).name.casefold() == "telegram.exe"
                    elif key in {"telegram_uni", "телеграм_юни"}:
                        is_telegram = executable_path == uni_path
                    else:
                        is_telegram = executable_path == user_path
                except Exception:
                    is_telegram = False
            is_browser = (
                key in {"browser", "браузер", "yandex", "яндекс"}
                and class_name == "Chrome_Yandex_WidgetWin_1"
            )
            if not is_browser and key in {"chrome", "браузер", "хром", "yandex", "яндекс", "edge"} and class_name in {
                "Chrome_WidgetWin_1",
                "Chrome_Yandex_WidgetWin_1",
            }:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False,
                        pid,
                    )
                    executable_name = Path(win32process.GetModuleFileNameEx(process, 0)).name.casefold()
                    expected = {
                        "chrome": {"chrome.exe"},
                        "хром": {"chrome.exe"},
                        "yandex": {"browser.exe"},
                        "яндекс": {"browser.exe"},
                        "edge": {"msedge.exe"},
                        "браузер": {"chrome.exe", "browser.exe", "msedge.exe"},
                    }[key]
                    is_browser = executable_name in expected
                except Exception:
                    is_browser = False
            if is_telegram or is_browser:
                matches.append((hwnd, title))

        win32gui.EnumWindows(callback, None)
        if len(matches) != 1:
            if key in {"telegram", "телеграм"} and len(matches) > 1:
                return False, "Найдено несколько Telegram-клиентов; укажите telegram_uni или telegram_user"
            return False, f"Ожидалось одно главное окно {app_name!r}, найдено: {len(matches)}"
        hwnd, title = matches[0]
        ComputerCapability._activate_window(hwnd)
        return True, title

    async def focus_app(self, app_name: str) -> ToolResult:
        try:
            success, detail = await asyncio.to_thread(self._focus_app, app_name)
            return ToolResult(success=success, message=(f"Приложение активно: {detail}" if success else detail))
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка фокуса приложения: {exc}")

    @staticmethod
    def _find_accessible_element(name: str, control_type: str = "") -> dict[str, Any] | None:
        """Find a visible named UI Automation element in the foreground window."""
        comtypes.CoInitialize()
        try:
            return ComputerCapability._find_accessible_element_initialized(name, control_type)
        finally:
            comtypes.CoUninitialize()

    @staticmethod
    def _find_accessible_element_initialized(name: str, control_type: str = "") -> dict[str, Any] | None:
        target = name.casefold().strip().strip("\u200e\u200f\u202a\u202b\u202c\u202d\u202e")
        if not target:
            return None

        control_types = {
            "button": uia.UIA_ButtonControlTypeId,
            "edit": uia.UIA_EditControlTypeId,
            "list_item": uia.UIA_ListItemControlTypeId,
        }
        wanted_type = control_types.get(control_type.casefold().strip())
        automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
        elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
        screen_width, screen_height = pyautogui.size()
        candidates: list[tuple[int, float, dict[str, Any]]] = []

        for index in range(elements.Length):
            element = elements.GetElement(index)
            try:
                candidate_name = (element.CurrentName or "").strip().strip(
                    "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
                )
                folded = candidate_name.casefold()
                if folded == target:
                    name_score = 300
                elif folded.startswith(target):
                    name_score = 200
                elif target in folded:
                    name_score = 100
                else:
                    continue
                candidate_type = element.CurrentControlType
                if wanted_type is not None and candidate_type != wanted_type:
                    continue
                rect = element.CurrentBoundingRectangle
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                width, height = right - left, bottom - top
                center_x, center_y = left + width / 2, top + height / 2
                if width <= 0 or height <= 0:
                    continue
                if not (0 <= center_x < screen_width and 0 <= center_y < screen_height):
                    continue
                area = float(width * height)
                candidates.append(
                    (
                        name_score,
                        area,
                        {
                            "x": float(left),
                            "y": float(top),
                            "width": float(width),
                            "height": float(height),
                            "confidence": 1.0,
                            "source": "accessibility",
                            "accessible_name": candidate_name,
                        },
                    )
                )
            except (AttributeError, OSError, ValueError):
                continue

        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][2]

    async def find_accessible_element(self, name: str, control_type: str = "") -> ToolResult:
        try:
            data = await asyncio.to_thread(self._find_accessible_element, name, control_type)
            if data is None:
                return ToolResult(success=False, message=f"Видимый элемент {name!r} не найден через Accessibility")
            return ToolResult(success=True, data=data, message=f"Уточнён центр видимого элемента {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка Accessibility-локатора: {exc}")

    @staticmethod
    def _focus_accessible_element(name: str, control_type: str = "") -> dict[str, Any]:
        comtypes.CoInitialize()
        try:
            target = name.casefold().strip()
            control_types = {
                "button": uia.UIA_ButtonControlTypeId,
                "edit": uia.UIA_EditControlTypeId,
                "list_item": uia.UIA_ListItemControlTypeId,
            }
            wanted_type = control_types.get(control_type.casefold().strip())
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            screen_width, screen_height = pyautogui.size()
            candidates: list[tuple[float, Any, dict[str, Any]]] = []
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    if (element.CurrentName or "").casefold().strip() != target:
                        continue
                    if wanted_type is not None and element.CurrentControlType != wanted_type:
                        continue
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    center_x, center_y = rect.left + width / 2, rect.top + height / 2
                    if width <= 0 or height <= 0:
                        continue
                    if not (0 <= center_x < screen_width and 0 <= center_y < screen_height):
                        continue
                    data = {
                        "x": float(rect.left),
                        "y": float(rect.top),
                        "width": float(width),
                        "height": float(height),
                        "accessible_name": str(element.CurrentName or "").strip(),
                    }
                    candidates.append((float(width * height), element, data))
                except (AttributeError, OSError, ValueError):
                    continue
            if not candidates:
                raise ValueError(f"Видимый элемент {name!r} не найден")
            candidates.sort(key=lambda item: item[0])
            element = candidates[0][1]
            element.SetFocus()
            time.sleep(0.25)
            return candidates[0][2]
        finally:
            comtypes.CoUninitialize()

    async def focus_accessible_element(self, name: str, control_type: str = "") -> ToolResult:
        try:
            data = await asyncio.to_thread(self._focus_accessible_element, name, control_type)
            return ToolResult(success=True, data=data, message=f"Фокус установлен на элемент {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка фокуса Accessibility-элемента: {exc}")

    @staticmethod
    def _resolve_accessible_action_target_initialized(
        name: str, control_type: str = "", automation_id: str = "",
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        clean = lambda value: str(value or "").strip().strip(
            "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
        )
        target = clean(name).casefold()
        if not target:
            raise ValueError("accessible_name_required")
        role_ids = {
            "button": uia.UIA_ButtonControlTypeId,
            "menu_item": uia.UIA_MenuItemControlTypeId,
            "link": uia.UIA_HyperlinkControlTypeId,
            "tab": uia.UIA_TabItemControlTypeId,
            "list_item": uia.UIA_ListItemControlTypeId,
            "checkbox": uia.UIA_CheckBoxControlTypeId,
            "radio": uia.UIA_RadioButtonControlTypeId,
            "combobox": uia.UIA_ComboBoxControlTypeId,
            "textbox": uia.UIA_EditControlTypeId,
        }
        wanted_type = role_ids.get(control_type.casefold().strip())
        automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            raise ValueError("foreground_window_missing")
        root = automation.ElementFromHandle(hwnd)
        elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
        expected_center = None
        if None not in (x, y, width, height):
            expected_center = (float(x) + float(width) / 2, float(y) + float(height) / 2)
        vx, vy = win32api.GetSystemMetrics(76), win32api.GetSystemMetrics(77)
        vw, vh = win32api.GetSystemMetrics(78), win32api.GetSystemMetrics(79)
        candidates: list[tuple[float, float, Any, dict[str, Any]]] = []
        for index in range(elements.Length):
            element = elements.GetElement(index)
            try:
                if clean(element.CurrentName).casefold() != target or not element.CurrentIsEnabled:
                    continue
                if wanted_type is not None and element.CurrentControlType != wanted_type:
                    continue
                candidate_id = clean(element.CurrentAutomationId)
                if automation_id and candidate_id != automation_id:
                    continue
                rect = element.CurrentBoundingRectangle
                w, h = rect.right - rect.left, rect.bottom - rect.top
                cx, cy = rect.left + w / 2, rect.top + h / 2
                if w <= 0 or h <= 0 or not (vx <= cx < vx + vw and vy <= cy < vy + vh):
                    continue
                distance = 0.0
                if expected_center is not None:
                    distance = (cx - expected_center[0]) ** 2 + (cy - expected_center[1]) ** 2
                data = {
                    "name": clean(element.CurrentName),
                    "automation_id": candidate_id,
                    "control_type_id": int(element.CurrentControlType),
                    "x": float(rect.left), "y": float(rect.top),
                    "width": float(w), "height": float(h),
                }
                candidates.append((distance, float(w * h), element, data))
            except (AttributeError, OSError, ValueError):
                continue
        if not candidates:
            raise ValueError(f"accessible_target_not_found: {name}")
        candidates.sort(key=lambda item: (item[0], item[1]))
        if expected_center is None and not automation_id and len(candidates) > 1:
            raise ValueError(f"accessible_target_ambiguous: {name}")
        return candidates[0][2], candidates[0][3]

    @staticmethod
    def _invoke_accessible_element(
        name: str, control_type: str = "", automation_id: str = "",
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
    ) -> dict[str, Any]:
        comtypes.CoInitialize()
        try:
            clean = lambda value: str(value or "").strip().strip("\u200e\u200f\u202a\u202b\u202c\u202d\u202e")
            target = clean(name).casefold()
            if not target:
                raise ValueError("accessible_name_required")
            role_ids = {
                "button": uia.UIA_ButtonControlTypeId, "menu_item": uia.UIA_MenuItemControlTypeId,
                "link": uia.UIA_HyperlinkControlTypeId, "tab": uia.UIA_TabItemControlTypeId,
                "list_item": uia.UIA_ListItemControlTypeId, "checkbox": uia.UIA_CheckBoxControlTypeId,
                "radio": uia.UIA_RadioButtonControlTypeId,
            }
            wanted_type = role_ids.get(control_type.casefold().strip())
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                raise ValueError("foreground_window_missing")
            root = automation.ElementFromHandle(hwnd)
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            expected_center = None
            if None not in (x, y, width, height):
                expected_center = (float(x) + float(width) / 2, float(y) + float(height) / 2)
            vx, vy = win32api.GetSystemMetrics(76), win32api.GetSystemMetrics(77)
            vw, vh = win32api.GetSystemMetrics(78), win32api.GetSystemMetrics(79)
            candidates = []
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    if clean(element.CurrentName).casefold() != target or not element.CurrentIsEnabled:
                        continue
                    if wanted_type is not None and element.CurrentControlType != wanted_type:
                        continue
                    candidate_id = clean(element.CurrentAutomationId)
                    if automation_id and candidate_id != automation_id:
                        continue
                    rect = element.CurrentBoundingRectangle
                    w, h = rect.right - rect.left, rect.bottom - rect.top
                    cx, cy = rect.left + w / 2, rect.top + h / 2
                    if w <= 0 or h <= 0 or not (vx <= cx < vx + vw and vy <= cy < vy + vh):
                        continue
                    distance = 0.0 if expected_center is None else (cx-expected_center[0])**2 + (cy-expected_center[1])**2
                    candidates.append((distance, float(w*h), element, {
                        "name": clean(element.CurrentName), "automation_id": candidate_id,
                        "control_type_id": int(element.CurrentControlType),
                    }))
                except (AttributeError, OSError, ValueError):
                    continue
            if not candidates:
                raise ValueError(f"accessible_target_not_found: {name}")
            candidates.sort(key=lambda item: (item[0], item[1]))
            if expected_center is None and not automation_id and len(candidates) > 1:
                raise ValueError(f"accessible_target_ambiguous: {name}")
            element, data = candidates[0][2], candidates[0][3]
            last_error = None
            for pattern_id, interface, invoke in (
                (uia.UIA_InvokePatternId, uia.IUIAutomationInvokePattern, lambda p: p.Invoke()),
                (uia.UIA_LegacyIAccessiblePatternId, uia.IUIAutomationLegacyIAccessiblePattern, lambda p: p.DoDefaultAction()),
            ):
                try:
                    invoke(element.GetCurrentPattern(pattern_id).QueryInterface(interface))
                    time.sleep(0.1)
                    data["invoked"] = True
                    return data
                except Exception as exc:
                    last_error = exc
            raise ValueError(f"accessible_target_not_invokable: {last_error}")
        finally:
            comtypes.CoUninitialize()

    async def invoke_accessible_element(self, name: str, control_type: str = "", **identity: Any) -> ToolResult:
        try:
            data = await asyncio.to_thread(self._invoke_accessible_element, name, control_type, **identity)
            return ToolResult(success=True, data=data, message=f"UIA Invoke выполнен: {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"UIA Invoke недоступен: {exc}")

    @staticmethod
    def _set_accessible_checked(
        name: str, checked: bool, control_type: str = "checkbox", **identity: Any,
    ) -> dict[str, Any]:
        comtypes.CoInitialize()
        try:
            element, data = ComputerCapability._resolve_accessible_action_target_initialized(
                name, control_type, **identity,
            )
            pattern = element.GetCurrentPattern(uia.UIA_TogglePatternId).QueryInterface(
                uia.IUIAutomationTogglePattern
            )
            desired = bool(checked)
            current = int(pattern.CurrentToggleState) == 1
            if current != desired:
                pattern.Toggle()
                time.sleep(0.1)
            observed = int(pattern.CurrentToggleState) == 1
            if observed != desired:
                raise ValueError("accessible_toggle_state_mismatch")
            data["checked"] = observed
            return data
        finally:
            comtypes.CoUninitialize()

    @staticmethod
    def _select_accessible_value(
        name: str, value: str, control_type: str = "combobox", **identity: Any,
    ) -> dict[str, Any]:
        comtypes.CoInitialize()
        try:
            wanted = str(value)
            if not wanted:
                raise ValueError("accessible_selection_value_required")
            element, data = ComputerCapability._resolve_accessible_action_target_initialized(
                name, control_type, **identity,
            )
            last_error: Exception | None = None
            try:
                pattern = element.GetCurrentPattern(uia.UIA_ValuePatternId).QueryInterface(
                    uia.IUIAutomationValuePattern
                )
                pattern.SetValue(wanted)
                time.sleep(0.1)
                if str(pattern.CurrentValue or "") == wanted:
                    data["value"] = wanted
                    return data
            except Exception as exc:
                last_error = exc
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            try:
                expand = element.GetCurrentPattern(uia.UIA_ExpandCollapsePatternId).QueryInterface(
                    uia.IUIAutomationExpandCollapsePattern
                )
                expand.Expand()
                time.sleep(0.1)
            except Exception as exc:
                last_error = exc
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            matches: list[Any] = []
            for index in range(elements.Length):
                item = elements.GetElement(index)
                try:
                    if item.CurrentControlType != uia.UIA_ListItemControlTypeId:
                        continue
                    if str(item.CurrentName or "").strip() != wanted or not item.CurrentIsEnabled:
                        continue
                    matches.append(item)
                except Exception:
                    continue
            if len(matches) != 1:
                raise ValueError(f"accessible_selection_not_unique: {wanted}; last={last_error}")
            item = matches[0]
            try:
                selection = item.GetCurrentPattern(uia.UIA_SelectionItemPatternId).QueryInterface(
                    uia.IUIAutomationSelectionItemPattern
                )
                selection.Select()
            except Exception:
                legacy = item.GetCurrentPattern(uia.UIA_LegacyIAccessiblePatternId).QueryInterface(
                    uia.IUIAutomationLegacyIAccessiblePattern
                )
                legacy.DoDefaultAction()
            time.sleep(0.1)
            try:
                expand.Collapse()
            except Exception:
                pass
            try:
                current = element.GetCurrentPattern(uia.UIA_ValuePatternId).QueryInterface(
                    uia.IUIAutomationValuePattern
                )
                observed = str(current.CurrentValue or "")
            except Exception:
                observed = wanted
            if observed != wanted:
                raise ValueError(f"accessible_selection_state_mismatch: {observed!r}")
            data["value"] = observed
            return data
        finally:
            comtypes.CoUninitialize()

    async def set_accessible_checked(
        self, name: str, checked: bool, control_type: str = "checkbox", **identity: Any,
    ) -> ToolResult:
        try:
            data = await asyncio.to_thread(
                self._set_accessible_checked, name, checked, control_type, **identity,
            )
            return ToolResult(success=True, data=data, message=f"UIA toggle подтверждён: {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"UIA toggle недоступен: {exc}")

    async def select_accessible_value(
        self, name: str, value: str, control_type: str = "combobox", **identity: Any,
    ) -> ToolResult:
        try:
            data = await asyncio.to_thread(
                self._select_accessible_value, name, value, control_type, **identity,
            )
            return ToolResult(success=True, data=data, message=f"UIA selection подтверждён: {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"UIA selection недоступен: {exc}")

    @staticmethod
    def _accessible_value(name: str, new_value: str | None = None) -> str:
        comtypes.CoInitialize()
        try:
            target = name.casefold().strip()
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            matches: list[tuple[float, Any]] = []
            screen_width, screen_height = pyautogui.size()
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    if element.CurrentControlType != uia.UIA_EditControlTypeId:
                        continue
                    if (element.CurrentName or "").casefold().strip() != target:
                        continue
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    center_x, center_y = rect.left + width / 2, rect.top + height / 2
                    if width <= 0 or height <= 0:
                        continue
                    if not (0 <= center_x < screen_width and 0 <= center_y < screen_height):
                        continue
                    matches.append((float(width * height), element))
                except (AttributeError, OSError, ValueError):
                    continue
            if not matches:
                raise ValueError(f"Видимое поле {name!r} не найдено")
            matches.sort(key=lambda item: item[0])
            element = matches[0][1]
            if new_value is not None:
                element.SetFocus()
                time.sleep(0.1)
                setters = (
                    (uia.UIA_ValuePatternId, uia.IUIAutomationValuePattern),
                    (uia.UIA_LegacyIAccessiblePatternId, uia.IUIAutomationLegacyIAccessiblePattern),
                )
                last_error: Exception | None = None
                for pattern_id, interface in setters:
                    try:
                        pattern = element.GetCurrentPattern(pattern_id).QueryInterface(interface)
                        pattern.SetValue(new_value)
                        time.sleep(0.25)
                        return new_value
                    except Exception as exc:
                        last_error = exc
                raise ValueError(f"Поле не поддерживает установку значения: {last_error}")
            readers = (
                (uia.UIA_TextPatternId, uia.IUIAutomationTextPattern, lambda pattern: pattern.DocumentRange.GetText(-1)),
                (uia.UIA_ValuePatternId, uia.IUIAutomationValuePattern, lambda pattern: pattern.CurrentValue),
                (
                    uia.UIA_LegacyIAccessiblePatternId,
                    uia.IUIAutomationLegacyIAccessiblePattern,
                    lambda pattern: pattern.CurrentValue,
                ),
            )
            last_error: Exception | None = None
            empty_value_seen = False
            for pattern_id, interface, reader in readers:
                try:
                    pattern = element.GetCurrentPattern(pattern_id).QueryInterface(interface)
                    value = str(reader(pattern) or "")
                    if value:
                        return value
                    empty_value_seen = True
                except Exception as exc:
                    last_error = exc
            if empty_value_seen:
                return ""
            raise ValueError(f"Поле не поддерживает чтение значения: {last_error}")
        finally:
            comtypes.CoUninitialize()

    @staticmethod
    def _send_unicode(text: str, interval: float = 0.025) -> None:
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = (
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            )

        class INPUTUNION(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT),)

        class INPUT(ctypes.Structure):
            _fields_ = (("type", ctypes.c_ulong), ("union", INPUTUNION))

        key_up = 0x0002
        unicode_key = 0x0004
        units = [int.from_bytes(text.encode("utf-16-le")[index:index + 2], "little") for index in range(0, len(text.encode("utf-16-le")), 2)]
        for unit in units:
            for flags in (unicode_key, unicode_key | key_up):
                event = INPUT(type=1, union=INPUTUNION(ki=KEYBDINPUT(0, unit, flags, 0, None)))
                if ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
                    raise OSError("SendInput rejected a Unicode key event")
            time.sleep(interval)

    @staticmethod
    def _replace_accessible_text(name: str, text: str) -> str:
        comtypes.CoInitialize()
        try:
            target = name.casefold().strip()
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            candidates: list[tuple[float, Any]] = []
            screen_width, screen_height = pyautogui.size()
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    if element.CurrentControlType != uia.UIA_EditControlTypeId:
                        continue
                    if (element.CurrentName or "").casefold().strip() != target:
                        continue
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    center_x, center_y = rect.left + width / 2, rect.top + height / 2
                    if width > 0 and height > 0 and 0 <= center_x < screen_width and 0 <= center_y < screen_height:
                        candidates.append((float(width * height), element))
                except (AttributeError, OSError, ValueError):
                    continue
            if not candidates:
                raise ValueError(f"Видимое поле {name!r} не найдено")
            candidates.sort(key=lambda item: item[0])
            element = candidates[0][1]
            element.SetFocus()
            text_pattern = element.GetCurrentPattern(uia.UIA_TextPatternId).QueryInterface(
                uia.IUIAutomationTextPattern
            )
            text_pattern.DocumentRange.Select()
            time.sleep(0.1)
            ComputerCapability._send_unicode(text)
            time.sleep(0.4)
            fresh_pattern = element.GetCurrentPattern(uia.UIA_TextPatternId).QueryInterface(
                uia.IUIAutomationTextPattern
            )
            return str(fresh_pattern.DocumentRange.GetText(-1))
        finally:
            comtypes.CoUninitialize()

    async def read_accessible_value(self, name: str) -> ToolResult:
        try:
            value = await asyncio.to_thread(self._accessible_value, name)
            return ToolResult(success=True, data={"value": value}, message=f"Прочитано значение поля {name!r}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения поля: {exc}")

    async def set_accessible_value(self, name: str, text: str) -> ToolResult:
        try:
            value = await asyncio.to_thread(self._accessible_value, name, text)
            if value != text:
                return ToolResult(success=False, message="Accessibility не подтвердил установленный текст")
            return ToolResult(success=True, data={"value": value}, message=f"Текст поля {name!r} установлен")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка установки текста поля: {exc}")

    async def replace_accessible_text(self, name: str, text: str) -> ToolResult:
        try:
            value = await asyncio.to_thread(self._replace_accessible_text, name, text)
            if value != text:
                return ToolResult(success=False, data={"value": value}, message="Unicode-ввод не совпал с заданным текстом")
            return ToolResult(success=True, data={"value": value}, message=f"Unicode-текст поля {name!r} подтверждён")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка Unicode-ввода: {exc}")

    @staticmethod
    def _read_accessible_text(max_chars: int) -> str:
        comtypes.CoInitialize()
        try:
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            screen_width, screen_height = pyautogui.size()
            lines: list[str] = []
            seen: set[str] = set()
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    name = (element.CurrentName or "").strip()
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    center_x, center_y = rect.left + width / 2, rect.top + height / 2
                    if not name or width <= 0 or height <= 0:
                        continue
                    if not (0 <= center_x < screen_width and 0 <= center_y < screen_height):
                        continue
                    normalized = " ".join(name.split())
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    lines.append(normalized)
                    if sum(len(line) + 1 for line in lines) >= max_chars:
                        break
                except (AttributeError, OSError, ValueError):
                    continue
            return "\n".join(lines)[:max_chars]
        finally:
            comtypes.CoUninitialize()

    async def read_accessible_text(self, max_chars: int = 12000) -> ToolResult:
        try:
            text = await asyncio.to_thread(self._read_accessible_text, max(500, min(max_chars, 20000)))
            if not text:
                return ToolResult(success=False, message="В активном окне нет доступного видимого текста")
            return ToolResult(success=True, data={"text": text}, message="Видимый текст активного окна прочитан")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения активного окна: {exc}")

    @staticmethod
    def _read_focused_accessible_text() -> dict[str, str]:
        """Read the focused UIA element without searching by a fragile localized name."""
        comtypes.CoInitialize()
        try:
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            element = automation.GetFocusedElement()
            if element is None:
                raise ValueError("Сфокусированный Accessibility-элемент не найден")
            name = str(element.CurrentName or "").strip()
            value = ""
            try:
                value_pattern = element.GetCurrentPattern(uia.UIA_ValuePatternId).QueryInterface(
                    uia.IUIAutomationValuePattern
                )
                value = str(value_pattern.CurrentValue or "")
            except (AttributeError, OSError):
                try:
                    text_pattern = element.GetCurrentPattern(uia.UIA_TextPatternId).QueryInterface(
                        uia.IUIAutomationTextPattern
                    )
                    value = str(text_pattern.DocumentRange.GetText(-1) or "")
                except (AttributeError, OSError):
                    pass
            if not name and not value:
                raise ValueError("Сфокусированный элемент не предоставляет текст")
            return {"name": name, "value": value}
        finally:
            comtypes.CoUninitialize()

    async def read_focused_accessible_text(self) -> ToolResult:
        try:
            data = await asyncio.to_thread(self._read_focused_accessible_text)
            return ToolResult(success=True, data=data, message="Текст сфокусированного элемента прочитан")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения сфокусированного элемента: {exc}")

    @staticmethod
    def _list_accessible_fields(max_fields: int) -> list[dict[str, Any]]:
        """List visible edit controls and their values for bounded UI diagnosis."""
        comtypes.CoInitialize()
        try:
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            root = automation.ElementFromHandle(win32gui.GetForegroundWindow())
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            screen_width, screen_height = pyautogui.size()
            fields: list[dict[str, Any]] = []
            for index in range(elements.Length):
                element = elements.GetElement(index)
                try:
                    if element.CurrentControlType != uia.UIA_EditControlTypeId:
                        continue
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    center_x, center_y = rect.left + width / 2, rect.top + height / 2
                    if width <= 0 or height <= 0:
                        continue
                    if not (0 <= center_x < screen_width and 0 <= center_y < screen_height):
                        continue
                    value = ""
                    try:
                        pattern = element.GetCurrentPattern(uia.UIA_ValuePatternId).QueryInterface(
                            uia.IUIAutomationValuePattern
                        )
                        value = str(pattern.CurrentValue or "")
                    except Exception:
                        try:
                            pattern = element.GetCurrentPattern(uia.UIA_TextPatternId).QueryInterface(
                                uia.IUIAutomationTextPattern
                            )
                            value = str(pattern.DocumentRange.GetText(-1) or "")
                        except Exception:
                            pass
                    fields.append(
                        {
                            "name": str(element.CurrentName or "").strip(),
                            "value": value[:4000],
                            "x": float(rect.left),
                            "y": float(rect.top),
                            "width": float(width),
                            "height": float(height),
                        }
                    )
                    if len(fields) >= max_fields:
                        break
                except (AttributeError, OSError, ValueError):
                    continue
            return fields
        finally:
            comtypes.CoUninitialize()

    async def list_accessible_fields(self, max_fields: int = 50) -> ToolResult:
        try:
            fields = await asyncio.to_thread(self._list_accessible_fields, max(1, min(max_fields, 100)))
            return ToolResult(
                success=True,
                data={"fields": fields},
                message=f"Найдено видимых текстовых полей: {len(fields)}",
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка чтения текстовых полей: {exc}")

    @staticmethod
    def _inspect_accessible_elements(max_elements: int = 120) -> dict[str, Any]:
        """Return a bounded semantic UIA snapshot of the foreground window."""
        comtypes.CoInitialize()
        try:
            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                raise ValueError("foreground_window_missing")
            root = automation.ElementFromHandle(hwnd)
            elements = root.FindAll(uia.TreeScope_Subtree, automation.CreateTrueCondition())
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            vx = win32api.GetSystemMetrics(76)
            vy = win32api.GetSystemMetrics(77)
            vw = win32api.GetSystemMetrics(78)
            vh = win32api.GetSystemMetrics(79)
            roles = {
                uia.UIA_ButtonControlTypeId: "button",
                uia.UIA_EditControlTypeId: "textbox",
                uia.UIA_HyperlinkControlTypeId: "link",
                uia.UIA_CheckBoxControlTypeId: "checkbox",
                uia.UIA_RadioButtonControlTypeId: "radio",
                uia.UIA_ComboBoxControlTypeId: "combobox",
                uia.UIA_ListItemControlTypeId: "list_item",
                uia.UIA_MenuItemControlTypeId: "menu_item",
                uia.UIA_TabItemControlTypeId: "tab",
                uia.UIA_TreeItemControlTypeId: "tree_item",
                uia.UIA_DataItemControlTypeId: "data_item",
                uia.UIA_SliderControlTypeId: "slider",
                uia.UIA_TextControlTypeId: "text",
            }
            out: list[dict[str, Any]] = []
            limit = max(1, min(int(max_elements), 200))
            for index in range(elements.Length):
                if len(out) >= limit:
                    break
                element = elements.GetElement(index)
                try:
                    rect = element.CurrentBoundingRectangle
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    cx, cy = rect.left + width / 2, rect.top + height / 2
                    if width <= 0 or height <= 0:
                        continue
                    if not (vx <= cx < vx + vw and vy <= cy < vy + vh):
                        continue
                    name = str(element.CurrentName or "").strip()
                    role = roles.get(element.CurrentControlType, "unknown")
                    automation_id = str(element.CurrentAutomationId or "").strip()
                    class_name = str(element.CurrentClassName or "").strip()
                    sensitive = bool(getattr(element, "CurrentIsPassword", False))
                    value = None
                    checked = None
                    if not sensitive and role in {"textbox", "combobox", "slider"}:
                        try:
                            pattern = element.GetCurrentPattern(uia.UIA_ValuePatternId).QueryInterface(
                                uia.IUIAutomationValuePattern
                            )
                            value = str(pattern.CurrentValue or "")[:4000]
                        except Exception:
                            pass
                    if role in {"checkbox", "radio"}:
                        try:
                            pattern = element.GetCurrentPattern(uia.UIA_TogglePatternId).QueryInterface(
                                uia.IUIAutomationTogglePattern
                            )
                            checked = int(pattern.CurrentToggleState) == 1
                        except Exception:
                            pass
                    if not name and not automation_id and role == "unknown":
                        continue
                    out.append({
                        "name": name, "text": name, "role": role,
                        "x": float(rect.left), "y": float(rect.top),
                        "width": float(width), "height": float(height),
                        "enabled": bool(element.CurrentIsEnabled), "value": value, "checked": checked,
                        "automation_id": automation_id, "class_name": class_name,
                        "control_type_id": int(element.CurrentControlType), "sensitive": sensitive,
                    })
                except (AttributeError, OSError, ValueError):
                    continue
            return {
                "active_window": {
                    "title": win32gui.GetWindowText(hwnd), "hwnd": int(hwnd), "pid": int(pid),
                    "class_name": win32gui.GetClassName(hwnd), "active": True,
                },
                "elements": out,
            }
        finally:
            comtypes.CoUninitialize()

    async def inspect_accessible_elements(self, max_elements: int = 120) -> ToolResult:
        try:
            data = await asyncio.to_thread(self._inspect_accessible_elements, max_elements)
            return ToolResult(success=True, data=data, message=f"UIA elements: {len(data['elements'])}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка UIA snapshot: {exc}")

    @staticmethod
    def _list_visible_windows() -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []

        def callback(hwnd, _extra):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = win32api.OpenProcess(
                    win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                    False,
                    pid,
                )
                executable = Path(win32process.GetModuleFileNameEx(process, 0)).name
            except Exception:
                executable = "unknown"
            windows.append(
                {
                    "title": title[:300],
                    "executable": executable,
                    "class_name": win32gui.GetClassName(hwnd),
                }
            )

        win32gui.EnumWindows(callback, None)
        return windows

    async def list_visible_windows(self) -> ToolResult:
        try:
            windows = await asyncio.to_thread(self._list_visible_windows)
            return ToolResult(success=True, data={"windows": windows}, message=f"Найдено видимых окон: {len(windows)}")
        except Exception as exc:
            return ToolResult(success=False, message=f"Ошибка списка окон: {exc}")

    async def press_key(self, key: str) -> ToolResult:
        try:
            await asyncio.to_thread(pyautogui.hotkey, *key.split("+"))
            return ToolResult(success=True, message=f"Нажато: {key}")
        except Exception as e:
            return ToolResult(success=False, message=f"Ошибка: {e}")

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "launch":
            return await self.launch_app(kwargs.get("app", ""))
        elif action == "click":
            return await self.click(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("button", "left"))
        elif action == "move":
            return await self.move(kwargs.get("x", 0), kwargs.get("y", 0))
        elif action == "click_human":
            return await self.click_human(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("button", "left"))
        elif action == "double_click_human":
            return await self.double_click_human(kwargs.get("x", 0), kwargs.get("y", 0), kwargs.get("button", "left"))
        elif action == "drag_human":
            return await self.drag_human(
                kwargs.get("x1", 0), kwargs.get("y1", 0),
                kwargs.get("x2", 0), kwargs.get("y2", 0),
                kwargs.get("button", "left"),
            )
        elif action == "type":
            return await self.type_text(kwargs.get("text", ""), kwargs.get("interval", 0.05))
        elif action == "type_unicode":
            return await self.type_unicode(str(kwargs.get("text", "")), float(kwargs.get("interval", 0.01)))
        elif action == "press_window_hotkey":
            return await self.press_window_hotkey(str(kwargs.get("key", "")))
        elif action == "delete_backward":
            return await self.delete_backward(int(kwargs.get("count", 1000)))
        elif action == "paste":
            return await self.paste_text(str(kwargs.get("text", "")))
        elif action == "copy_selected_text":
            return await self.copy_selected_text()
        elif action == "focus_window":
            return await self.focus_window(str(kwargs.get("title", "")))
        elif action == "focus_app":
            return await self.focus_app(str(kwargs.get("app", "")))
        elif action == "find_accessible_element":
            return await self.find_accessible_element(
                str(kwargs.get("name", "")),
                str(kwargs.get("control_type", "")),
            )
        elif action == "focus_accessible_element":
            return await self.focus_accessible_element(
                str(kwargs.get("name", "")),
                str(kwargs.get("control_type", "")),
            )
        elif action == "invoke_accessible_element":
            identity = {key: kwargs[key] for key in ("automation_id", "x", "y", "width", "height") if key in kwargs}
            return await self.invoke_accessible_element(
                str(kwargs.get("name", "")), str(kwargs.get("control_type", "")), **identity
            )
        elif action == "set_accessible_checked":
            identity = {key: kwargs[key] for key in ("automation_id", "x", "y", "width", "height") if key in kwargs}
            return await self.set_accessible_checked(
                str(kwargs.get("name", "")), bool(kwargs.get("checked", False)),
                str(kwargs.get("control_type", "checkbox")), **identity,
            )
        elif action == "select_accessible_value":
            identity = {key: kwargs[key] for key in ("automation_id", "x", "y", "width", "height") if key in kwargs}
            return await self.select_accessible_value(
                str(kwargs.get("name", "")), str(kwargs.get("value", "")),
                str(kwargs.get("control_type", "combobox")), **identity,
            )
        elif action == "read_accessible_value":
            return await self.read_accessible_value(str(kwargs.get("name", "")))
        elif action == "set_accessible_value":
            return await self.set_accessible_value(
                str(kwargs.get("name", "")),
                str(kwargs.get("text", "")),
            )
        elif action == "replace_accessible_text":
            return await self.replace_accessible_text(
                str(kwargs.get("name", "")),
                str(kwargs.get("text", "")),
            )
        elif action == "read_accessible_text":
            return await self.read_accessible_text(int(kwargs.get("max_chars", 12000)))
        elif action == "read_focused_accessible_text":
            return await self.read_focused_accessible_text()
        elif action == "inspect_accessible_elements":
            return await self.inspect_accessible_elements(int(kwargs.get("max_elements", 120)))
        elif action == "list_accessible_fields":
            return await self.list_accessible_fields(int(kwargs.get("max_fields", 50)))
        elif action == "list_visible_windows":
            return await self.list_visible_windows()
        elif action == "press":
            return await self.press_key(kwargs.get("key", ""))
        # 🤖 Hermes (2026-08-14): режим мыши Юни — визуально-управляемая
        # автоматизация браузера через внешний Moondream-endpoint.
        # Старый execute (pyautogui/UIA-ветки) НЕ удалён — эти действия
        # добавлены аддитивно и срабатывают только при mouse_mode=True
        # либо по явному action-имени.
        elif action == "set_mouse_mode":
            self.set_mouse_mode(bool(kwargs.get("enabled", False)))
            return ToolResult(success=True, message=f"Режим мыши {'включён' if self.mouse_mode else 'выключен'}")
        elif action in ("open_browser", "open_new_tab", "type_url"):
            if not self.mouse_mode:
                return ToolResult(success=False, message="Режим мыши выключен (set_mouse_mode=true)")
            try:
                ba = self._browser_automation()
                if action == "open_browser":
                    ok = await ba.open_browser(str(kwargs.get("browser", "Яндекс")))
                    return ToolResult(success=bool(ok), message="Браузер открыт" if ok else "Не удалось открыть браузер", mode="mouse")
                if action == "open_new_tab":
                    ok = await ba.open_new_tab()
                    return ToolResult(success=ok, message="Новая вкладка открыта" if ok else "Не удалось открыть вкладку", mode="mouse")
                if action == "type_url":
                    ok = await ba.type_url(str(kwargs.get("url", "")))
                    return ToolResult(success=ok, message=f"URL введён" if ok else "Не удалось ввести URL", mode="mouse")
            except Exception as exc:
                return ToolResult(success=False, message=f"Ошибка мыши: {exc}", mode="mouse")
        return ToolResult(success=False, message=f"Неизвестное действие: {action}")
