# -*- mode: python ; coding: utf-8 -*-
"""One-dir build for Windows (easier to debug)."""

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.datastruct import Tree

APP_NAME = "GeradorEtiquetas"
ICON_PATH = os.path.join("assets", "color.ico")
block_cipher = None

# Hidden imports necessários (PyQt5, Pillow, pywin32)
hidden = []
hidden += collect_submodules("PyQt5")
hidden += collect_submodules("win32com")
hidden += collect_submodules("PIL")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],  # usaremos Tree("assets", ...) no COLLECT (recursivo)
    hiddenimports=hidden + ["pywintypes", "pythoncom", "win32timezone"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Em onedir, o padrão robusto é excluir binários aqui e reuni-los no COLLECT
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
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
    Tree("assets", prefix="assets"),  # inclui a pasta assets inteira no dist
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
