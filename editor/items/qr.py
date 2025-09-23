"""QR code preview item."""
from __future__ import annotations

import hashlib
from typing import Sequence

from qt_compat import QColor, QPainter, Qt

from .base import BaseLabelItem, PropertyField


class QRLabelItem(BaseLabelItem):
    """Draws a stylised QR code based on the item data."""

    ERROR_LEVELS = ["L", "M", "Q", "H"]

    def __init__(
        self,
        data: str = "",
        size: tuple[float, float] | None = None,
        error_level: str = "M",
        modules: int = 25,
        margin: float = 2.0,
        foreground: QColor | None = None,
        background: QColor | None = None,
    ) -> None:
        super().__init__(size)
        self._data = data or "https://example.com"
        self._error_level = error_level if error_level in self.ERROR_LEVELS else "M"
        self._modules = max(9, min(41, int(modules)))
        self._margin = max(0.0, float(margin))
        self._foreground = QColor(foreground or QColor(20, 20, 20))
        self._background = QColor(background or QColor(245, 245, 245))

    # ------------------------------------------------------------------
    def _matrix(self) -> list[str]:
        base = hashlib.sha256((self._error_level + "|" + self._data).encode("utf-8")).digest()
        bits = "".join(f"{b:08b}" for b in base)
        required = self._modules * self._modules
        if not bits:
            bits = "0"
        repeats = (required + len(bits) - 1) // len(bits)
        pattern = (bits * repeats)[:required]
        rows = [pattern[i : i + self._modules] for i in range(0, required, self._modules)]
        return rows

    def paint_content(self, painter: QPainter, rect):  # type: ignore[override]
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._background)
        painter.drawRect(rect)
        matrix = self._matrix()
        if not matrix:
            painter.restore()
            return
        available = min(rect.width(), rect.height())
        module_size = available / (self._modules + 2 * self._margin)
        start_x = rect.center().x() - (self._modules * module_size) / 2
        start_y = rect.center().y() - (self._modules * module_size) / 2
        painter.setBrush(self._foreground)
        for row, bits in enumerate(matrix):
            for col, bit in enumerate(bits):
                if bit == "1":
                    x = start_x + col * module_size
                    y = start_y + row * module_size
                    painter.drawRect(x, y, module_size, module_size)
        painter.restore()

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {
            "data": self._data,
            "error_level": self._error_level,
            "modules": self._modules,
            "margin": self._margin,
            "foreground": self._foreground.name(),
            "background": self._background.name(),
        }

    def apply_serialized_data(self, data) -> None:
        if not isinstance(data, dict):
            return
        self._data = str(data.get("data", self._data))
        level = data.get("error_level", self._error_level)
        if level in self.ERROR_LEVELS:
            self._error_level = level
        self._modules = max(9, min(41, int(data.get("modules", self._modules))))
        self._margin = max(0.0, float(data.get("margin", self._margin)))
        fg = data.get("foreground")
        bg = data.get("background")
        if fg:
            self._foreground = QColor(fg)
        if bg:
            self._background = QColor(bg)
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def property_fields(self) -> Sequence[PropertyField]:
        return [
            PropertyField("data", "Conteúdo", "text"),
            PropertyField("error_level", "Correção", "choice", options=self.ERROR_LEVELS),
            PropertyField("modules", "Módulos", "int", minimum=9, maximum=41, step=1),
            PropertyField("margin", "Margem", "float", minimum=0.0, maximum=10.0, step=0.5),
            PropertyField("foreground", "Cor", "color"),
            PropertyField("background", "Fundo", "color"),
        ]

    def property_values(self) -> dict:
        return {
            "data": self._data,
            "error_level": self._error_level,
            "modules": self._modules,
            "margin": self._margin,
            "foreground": self._foreground,
            "background": self._background,
        }

    def set_property(self, name: str, value) -> None:
        if name == "data":
            self._data = str(value)
        elif name == "error_level" and value in self.ERROR_LEVELS:
            self._error_level = str(value)
        elif name == "modules":
            self._modules = max(9, min(41, int(value)))
        elif name == "margin":
            self._margin = max(0.0, float(value))
        elif name == "foreground":
            self._foreground = QColor(value)
        elif name == "background":
            self._background = QColor(value)
        else:
            return
        self.update()
        self.notify_geometry_changed()
