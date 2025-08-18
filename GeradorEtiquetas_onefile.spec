
# -*- mode: python ; coding: utf-8 -*-
# One-file build for Windows (no console).
import os
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules
from _version import __version__

APP_NAME = "GeradorEtiquetas"
ICON_PATH = os.path.join("assets", "color.ico")

# Collect a few dynamic modules that PyInstaller sometimes misses
hidden = []
hidden += collect_submodules("PyQt5")
hidden += collect_submodules("win32com")
hidden += collect_submodules("PIL")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets" + os.sep + "*", "assets")],
    hiddenimports=hidden + ["pywintypes", "pythoncom", "win32timezone"],
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

# one-file builds do not use COLLECT; the .exe goes to dist/
