#!/usr/bin/env python3
"""Найти окно Electron оверлея и вывести его rect + заголовок (проверка BUG#3)."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

found = []

def enum_cb(hwnd, lparam):
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    # ищем Electron-оверлей (заголовок "UNI Desktop Companion" или класс Electron)
    if "UNI Desktop Companion" in title or "Electron" in cls.value:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        visible = user32.IsWindowVisible(hwnd)
        found.append((title, cls.value, rect.left, rect.top, rect.right, rect.bottom, visible))
    return True

EnumWindows(EnumWindowsProc(enum_cb), 0)
if not found:
    print("NO_ELECTRON_WINDOW")
else:
    for t in found:
        title, cls, l, tp, r, b, vis = t
        w, h = r - l, b - tp
        print(f"WIN title='{title}' class='{cls}' rect=({l},{tp})-({r},{b}) size={w}x{h} visible={vis}")
