"""Camada de compatibilidade entre bindings Qt.

Responsabilidade:
    Disponibilizar classes Qt usando PyQt5 ou PySide6 de forma uniforme.

Dependências:
    - PyQt5
    - PySide6

Exemplo:
    >>> from qt_compat import QApplication
    >>> app = QApplication([])
"""
from __future__ import annotations

# ruff: noqa: F403

QT_API = "PyQt5"

try:
    from PyQt5.QtCore import *  # type: ignore
    from PyQt5.QtGui import *  # type: ignore
    from PyQt5.QtWidgets import *  # type: ignore
except Exception:  # pragma: no cover - fallback
    QT_API = "PySide6"
    from PySide6 import QtCore  # type: ignore
    from PySide6.QtCore import *  # type: ignore
    from PySide6.QtGui import *  # type: ignore
    from PySide6.QtWidgets import *  # type: ignore

    # Provide PyQt5 compatible aliases
    pyqtSignal = QtCore.Signal
    pyqtSlot = QtCore.Slot  # noqa: F401

__all__ = [name for name in globals() if not name.startswith("_")]
