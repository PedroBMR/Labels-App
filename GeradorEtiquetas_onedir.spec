# -*- mode: python ; coding: utf-8 -*-
"""Spec file to build the GeradorEtiquetas application in onedir mode.

Designed for Python 3.13 on Windows 11, this configuration produces
a folder containing the executable and all its dependencies (used
by ``utils.recurso_caminho``), works with PyQt5 and pywin32 modules,
suppresses the console window and disables UPX compression for faster
development builds.

The final bundle is saved under ``dist/GeradorEtiquetas``.
"""

import os

# ---------------------------------------------------------------------------
# Basic project paths and metadata
APP_NAME = "GeradorEtiquetas"                 # Name of the generated .exe
MAIN_SCRIPT = "main.py"                        # Entry point of the program
ASSETS_DIR = "assets"                          # Folder bundled with the app
ICON_PATH = os.path.join(ASSETS_DIR, "color.ico")

# Explicit list of modules required at runtime.
hiddenimports = [
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "pywintypes",
    "pythoncom",
    "win32timezone",
    # PyWin32 modules used directly or by win32print
    "win32print",
    "win32api",
]

# Include the entire assets directory preserving structure
# Use a list of tuples to specify source and destination pairs
datas = [(ASSETS_DIR, ASSETS_DIR)]

# ---------------------------------------------------------------------------
# 1) Analyse the application and dependencies
block_cipher = None

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# 2) Package Python modules
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 3) Build the final onedir bundle
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # Disable UPX for faster iterative builds
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # Do not open a console window
    icon=ICON_PATH,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
    distpath="dist",    # Output folder for the bundle
)
