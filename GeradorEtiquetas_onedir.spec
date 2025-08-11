# -*- mode: python ; coding: utf-8 -*-
"""Spec file for building the application in onedir mode.

Useful for debugging; places the executable and resources in a folder.
"""

import os
from _version import __version__
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct,
)

# ------------------------------------------------------------------
# Configurable parameters
APP_NAME = os.environ.get("APP_NAME", "GeradorEtiquetas")
ICON_PATH = os.environ.get("APP_ICON", os.path.join("assets", "color.ico"))

# Version information
_ver_tuple = tuple(map(int, __version__.split("."))) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_ver_tuple,
        prodvers=_ver_tuple,
        mask=0x3F,
        flags=0x0,
        OS=0x4,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "CONIMS"),
                        StringStruct("FileDescription", "Gerador de Etiquetas CONIMS"),
                        StringStruct("FileVersion", __version__),
                        StringStruct("ProductVersion", __version__),
                        StringStruct("ProductName", "Gerador de Etiquetas"),
                        StringStruct("LegalCopyright", "Copyright (C) CONIMS"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])]),
    ],
)

# ------------------------------------------------------------------
# 1) Analyse sources and hidden imports
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["pyqt5", "PyQt5.sip", "win32print", "win32api", "win32ui"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# 2) Bundle Python bytecode
pyz = PYZ(a.pure)

# 3) Build executable (binaries excluded, collected later)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=ICON_PATH,
    version=version_info,
    upx=True,
    contents_directory=".",  # avoid _internal folder
    bootloader_runtime_opts=["--dpiaware", "--utf-8"],
)

# 4) Collect all dependencies and assets into dist/APP_NAME
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    Tree("assets", prefix="assets"),
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
