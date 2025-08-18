
# -*- mode: python ; coding: utf-8 -*-
One-file build for Windows (no console) — PySide6 (Python 3.13).
import os
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "GeradorEtiquetas"
ICON_PATH = os.path.join("assets", "color.ico")

hidden = []
hidden += collect_submodules("PySide6")
hidden += ["pywintypes", "pythoncom", "win32timezone"]  # pywin32 pieces

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets" + os.sep + "*", "assets")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON_PATH,
)
