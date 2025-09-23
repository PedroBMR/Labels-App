"""Primitive shape items."""
from __future__ import annotations

from typing import Sequence

from qt_compat import QColor, QPainter, Qt

from .base import BaseLabelItem, PropertyField


class ShapeLabelItem(BaseLabelItem):
    """Draws basic vector shapes."""

    SHAPES = ["rectangle", "ellipse", "rounded", "line"]

    def __init__(
        self,
        size: tuple[float, float] | None = None,
        shape: str = "rectangle",
        fill: QColor | None = None,
        stroke: QColor | None = None,
        stroke_width: float = 2.0,
        corner_radius: float = 8.0,
    ) -> None:
        super().__init__(size)
        self._shape = shape if shape in self.SHAPES else "rectangle"
        self._fill = QColor(fill or QColor(220, 220, 220, 120))
        self._stroke = QColor(stroke or QColor(60, 60, 60))
        self._stroke_width = max(0.2, float(stroke_width))
        self._corner_radius = max(0.0, float(corner_radius))

    # ------------------------------------------------------------------
    def paint_content(self, painter: QPainter, rect):  # type: ignore[override]
        painter.save()
        painter.setPen(self._stroke)
        painter.setBrush(self._fill)
        pen = painter.pen()
        pen.setWidthF(self._stroke_width)
        painter.setPen(pen)
        if self._shape == "ellipse":
            painter.drawEllipse(rect)
        elif self._shape == "rounded":
            radius = min(self._corner_radius, min(rect.width(), rect.height()) / 2)
            painter.drawRoundedRect(rect, radius, radius)
        elif self._shape == "line":
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        else:
            painter.drawRect(rect)
        painter.restore()

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {
            "shape": self._shape,
            "fill": self._fill.name(),
            "stroke": self._stroke.name(),
            "stroke_width": self._stroke_width,
            "corner_radius": self._corner_radius,
        }

    def apply_serialized_data(self, data) -> None:
        if not isinstance(data, dict):
            return
        shape = data.get("shape", self._shape)
        if shape in self.SHAPES:
            self._shape = shape
        fill = data.get("fill")
        stroke = data.get("stroke")
        if fill:
            self._fill = QColor(fill)
        if stroke:
            self._stroke = QColor(stroke)
        self._stroke_width = max(0.2, float(data.get("stroke_width", self._stroke_width)))
        self._corner_radius = max(0.0, float(data.get("corner_radius", self._corner_radius)))
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def property_fields(self) -> Sequence[PropertyField]:
        return [
            PropertyField("shape", "Forma", "choice", options=self.SHAPES),
            PropertyField("fill", "Preenchimento", "color"),
            PropertyField("stroke", "Contorno", "color"),
            PropertyField("stroke_width", "Espessura", "float", minimum=0.2, maximum=20.0, step=0.5),
            PropertyField("corner_radius", "Raio", "float", minimum=0.0, maximum=100.0, step=1.0),
        ]

    def property_values(self) -> dict:
        return {
            "shape": self._shape,
            "fill": self._fill,
            "stroke": self._stroke,
            "stroke_width": self._stroke_width,
            "corner_radius": self._corner_radius,
        }

    def set_property(self, name: str, value) -> None:
        if name == "shape" and value in self.SHAPES:
            self._shape = str(value)
        elif name == "fill":
            self._fill = QColor(value)
        elif name == "stroke":
            self._stroke = QColor(value)
        elif name == "stroke_width":
            self._stroke_width = max(0.2, float(value))
        elif name == "corner_radius":
            self._corner_radius = max(0.0, float(value))
        else:
            return
        self.update()
        self.notify_geometry_changed()
