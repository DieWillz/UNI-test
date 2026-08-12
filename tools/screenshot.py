#!/usr/bin/env python3
"""Win32 BitBlt screenshot (без внешних зависимостей, кроме PIL).
Сохраняет весь экран в PNG. Используется для визуального proof-of-work.

Usage: python tools/screenshot.py <out.png> [monitor=0]
"""
import sys
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def screenshot_all(out_path: str):
    user32.SetProcessDPIAware()
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if width == 0 or height == 0:
        # fallback: primary monitor
        left, top = 0, 0
        width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    hwindc = user32.GetWindowDC(0)
    srcdc = gdi32.CreateCompatibleDC(hwindc)
    bmp = gdi32.CreateCompatibleBitmap(hwindc, width, height)
    gdi32.SelectObject(srcdc, bmp)
    gdi32.BitBlt(srcdc, 0, 0, width, height, hwindc, left, top, SRCCOPY)

    from PIL import Image
    import io
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(srcdc, bmp, 0, height, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    img.convert("RGB").save(out_path, "PNG")

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(srcdc)
    gdi32.DeleteDC(hwindc)
    return out_path, (width, height)


# --- BITMAPINFO structs (минимально для GetDIBits) ---
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "screenshot.png"
    path, size = screenshot_all(out)
    print(f"SAVED {path} {size[0]}x{size[1]}")
