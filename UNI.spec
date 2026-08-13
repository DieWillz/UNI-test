# 🤖 UNI.spec — PyInstaller (ФАЗА 7, F-01: portable UNI.exe)
#
# Собирает исполняемый UNI.exe из точки входа uni.webui.server (он поднимает
# и WebUI :8787, и tray-меню «Показать/Выход», и watchdog серверов — см. server.py).
# Electron-оверлей и llama-server.exe НЕ замораживаются (внешние side-car файлы,
# копируются в dist/ рядом), чтобы не ломать их нативные зависимости.
#
# Сборка (на целевой Windows-машине, где установлен PyInstaller + нужные библиотеки):
#     pyinstaller UNI.spec --clean
# Результат: dist/UNI.exe (onefile, windowed — без консоли), + electron/ и
# runtime/llama/ копируются вручную/Inno Setup-ом.
#
# F-01 требования, отражённые здесь:
#  - onefile: yes (единый UNI.exe)
#  - windowed: True (без консолей)
#  - secrets: исключены (config.yaml НЕ в datas; кладётся config.example.yaml)
#  - относительные пути: entry использует sys._MEIPASS / _ROOT относительно exe

# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ROOT = os.path.abspath(SPECPATH)

# Данные, которые надо положить рядом с exe (относительные пути в dist/)
datas = []
# конфиг-пример (БЕЗ секретов)
if os.path.exists(os.path.join(ROOT, "config.example.yaml")):
    datas.append((os.path.join(ROOT, "config.example.yaml"), "."))
# ассеты оверлея (иконки, шрифты) — только нужное, без node_modules
for asset in ("assets",):
    src = os.path.join(ROOT, "uni", "desktop", "renderer", asset)
    if os.path.isdir(src):
        datas.append((src, "uni/desktop/renderer/assets"))
# шаблоны runtime (если есть)
for rt in ("runtime",):
    src = os.path.join(ROOT, rt)
    if os.path.isdir(src):
        # не класть логи/pid в дистрибутив
        datas.append((src, rt))

# Скрытые импорты: capability-модули лениво импортируются — PyInstaller их не видит
hiddenimports = collect_submodules("uni") + [
    "win32api", "win32gui", "win32con", "win32clipboard", "win32process",
    "comtypes", "comtypes.gen.UIAutomationClient",
    "tkinter", " PIL", "cv2", "numpy", "sounddevice", "soundfile",
    "faster_whisper", "piper", "openai", "gradio_client", "playwright",
    "buttplug", "mss", "yaml", "rich", "pyautogui",
]

# Исключения: не тащить node_modules, тесты, __pycache__, .git
excludes = [
    "node_modules", "pytest", "tests",
    "torch",  # большой; если не нужен в дистрибутиве офлайн — исключить
              # (при офлайн-TTS через piper/браузер torch не обязателен)
]

a = Analysis(
    [os.path.join(ROOT, "uni", "webui", "server.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="UNI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,           # F-01: без консолей
    windowed=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "uni", "desktop", "renderer", "assets", "uni.ico") if os.path.exists(os.path.join(ROOT, "uni", "desktop", "renderer", "assets", "uni.ico")) else None,
)
