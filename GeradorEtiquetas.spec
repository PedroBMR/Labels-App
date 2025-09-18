# -*- mode: python ; coding: utf-8 -*-
"""Spec file to build the GeradorEtiquetas application.

Designed for Python 3.13 on Windows 11, this configuration produces
a single executable that bundles the entire ``assets`` directory (used
by ``utils.recurso_caminho``), works with PyQt5 and pywin32 modules,
suppresses the console window and applies UPX compression.

The final executable is saved as ``dist/GeradorEtiquetas.exe``.
"""

import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.datastruct import Tree

# ---------------------------------------------------------------------------
# Basic project paths and metadata
APP_NAME = "GeradorEtiquetas"                 # Name of the generated .exe
MAIN_SCRIPT = "main.py"                        # Entry point of the program
ASSETS_DIR = "assets"                          # Folder bundled with the app
ICON_PATH = os.path.join(ASSETS_DIR, "color.ico")

# ----------------------------------------------------------------------------
# Qt binding configuration

QT_BINDING = os.environ.get("QT_BINDING", "PyQt5")

if QT_BINDING == "PySide6":
    qt_hiddenimports = ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    qt_excludes = ["PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"]
else:  # Default to PyQt5
    qt_hiddenimports = ["PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"]
    qt_excludes = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

qt_hiddenimports.extend(collect_submodules(QT_BINDING))
qt_hiddenimports.insert(0, QT_BINDING)

# Explicit list of modules required at runtime.
hiddenimports = qt_hiddenimports + [
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
    excludes=qt_excludes,
    noarchive=False,
)

# 2) Package Python modules
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 3) Build the final onefile executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,            # Use UPX if available to reduce size
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # Do not open a console window
    icon=ICON_PATH,
    disable_windowed_traceback=False,
    distpath="dist",     # Output folder for the executable
)
