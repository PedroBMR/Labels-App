"""Compat layer for Qt bindings.

Tries to import PyQt5 and falls back to PySide6, exposing the same names so
that the rest of the code can simply ``from qt_compat import ...``.
"""
from __future__ import annotations

QT_API = "PyQt5"

try:
    from PyQt5.QtCore import *  # type: ignore
    from PyQt5.QtGui import *  # type: ignore
    from PyQt5.QtWidgets import *  # type: ignore
except Exception:  # pragma: no cover - fallback
    QT_API = "PySide6"
    from PySide6.QtCore import *  # type: ignore
    from PySide6.QtGui import *  # type: ignore
    from PySide6.QtWidgets import *  # type: ignore

    # Provide PyQt5 compatible aliases
    from PySide6.QtCore import Signal as pyqtSignal, Slot as pyqtSlot  # type: ignore

__all__ = [name for name in globals() if not name.startswith("_")]
