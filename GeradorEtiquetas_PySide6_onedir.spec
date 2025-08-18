
# -*- mode: python ; coding: utf-8 -*-
One-dir build for Windows (easier to debug) — Python 3.13.
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(sys.argv[0])))
import qt_compat
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "GeradorEtiquetas"
ICON_PATH = os.path.join("assets", "color.ico")

hidden = []
hidden += collect_submodules(qt_compat.QT_API)
hidden += ["pywintypes", "pythoncom", "win32timezone"]

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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
