"""Barcode item representation."""
from __future__ import annotations

import hashlib
from typing import Sequence

from qt_compat import QColor, QPainter, Qt

from .base import BaseLabelItem, PropertyField


class BarcodeLabelItem(BaseLabelItem):
    """Simplified barcode preview with configurable symbology."""

    SYMBOLOGIES = ["Code128", "Code39", "EAN13", "EAN8", "Interleaved2of5"]

    def __init__(
        self,
        data: str = "1234567890",
        size: tuple[float, float] | None = None,
        symbology: str = "Code128",
        show_text: bool = True,
        bar_height: float = 0.75,
        foreground: QColor | None = None,
    ) -> None:
        super().__init__(size)
        self._data = data
        self._symbology = symbology if symbology in self.SYMBOLOGIES else "Code128"
        self._show_text = bool(show_text)
        self._bar_height = max(0.2, min(1.0, float(bar_height)))
        self._foreground = QColor(foreground or QColor(20, 20, 20))

    # ------------------------------------------------------------------
    def _pattern(self) -> str:
        base = hashlib.sha256((self._symbology + "|" + self._data).encode("utf-8")).digest()
        bits = "".join(f"{b:08b}" for b in base)
        target_len = 128
        if not bits:
            return "0" * target_len
        repeats = (target_len + len(bits) - 1) // len(bits)
        pattern = (bits * repeats)[:target_len]
        return pattern

    def paint_content(self, painter: QPainter, rect):  # type: ignore[override]
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._foreground)
        pattern = self._pattern()
        if not pattern:
            painter.restore()
            return
        bar_width = max(1.0, rect.width() / len(pattern))
        bar_height = rect.height() * self._bar_height
        y_start = rect.top()
        for index, bit in enumerate(pattern):
            if bit == "1":
                x = rect.left() + index * bar_width
                painter.drawRect(x, y_start, bar_width, bar_height)
        if self._show_text:
            painter.setPen(self._foreground)
            painter.setBrush(Qt.NoBrush)
            painter.drawText(rect.adjusted(0, bar_height, 0, 0), Qt.AlignCenter, self._data)
        painter.restore()

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {
            "data": self._data,
            "symbology": self._symbology,
            "show_text": self._show_text,
            "bar_height": self._bar_height,
            "foreground": self._foreground.name(),
        }

    def apply_serialized_data(self, data) -> None:
        if not isinstance(data, dict):
            return
        self._data = str(data.get("data", self._data))
        sym = data.get("symbology", self._symbology)
        if sym in self.SYMBOLOGIES:
            self._symbology = sym
        self._show_text = bool(data.get("show_text", self._show_text))
        self._bar_height = max(0.2, min(1.0, float(data.get("bar_height", self._bar_height))))
        fg = data.get("foreground")
        if fg:
            self._foreground = QColor(fg)
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def property_fields(self) -> Sequence[PropertyField]:
        return [
            PropertyField("data", "Conteúdo", "text"),
            PropertyField("symbology", "Simbologia", "choice", options=self.SYMBOLOGIES),
            PropertyField("show_text", "Mostrar texto", "bool"),
            PropertyField("bar_height", "Altura", "float", minimum=0.2, maximum=1.0, step=0.05),
            PropertyField("foreground", "Cor", "color"),
        ]

    def property_values(self) -> dict:
        return {
            "data": self._data,
            "symbology": self._symbology,
            "show_text": self._show_text,
            "bar_height": self._bar_height,
            "foreground": self._foreground,
        }

    def set_property(self, name: str, value) -> None:
        if name == "data":
            self._data = str(value)
        elif name == "symbology" and value in self.SYMBOLOGIES:
            self._symbology = str(value)
        elif name == "show_text":
            self._show_text = bool(value)
        elif name == "bar_height":
            self._bar_height = max(0.2, min(1.0, float(value)))
        elif name == "foreground":
            self._foreground = QColor(value)
        else:
            return
        self.update()
        self.notify_geometry_changed()
