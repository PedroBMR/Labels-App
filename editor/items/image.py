"""Image item for the editor."""
from __future__ import annotations

import os
from typing import Sequence

from qt_compat import QColor, QPainter, QPixmap, QRectF, Qt

from .base import BaseLabelItem, PropertyField


class ImageLabelItem(BaseLabelItem):
    """Displays an image with configurable fit modes."""

    FIT_MODES = ["contain", "cover", "stretch", "actual"]

    def __init__(
        self,
        source: str = "",
        size: tuple[float, float] | None = None,
        fit_mode: str = "contain",
        opacity: float = 1.0,
        background: QColor | None = None,
    ) -> None:
        super().__init__(size)
        self._source = source
        self._fit_mode = fit_mode if fit_mode in self.FIT_MODES else "contain"
        self._opacity = max(0.1, min(1.0, float(opacity)))
        self._background = QColor(background or QColor(235, 235, 235))
        self._pixmap = QPixmap()
        if self._source:
            self._load_pixmap()

    # ------------------------------------------------------------------
    def _load_pixmap(self) -> None:
        if self._source and os.path.exists(self._source):
            self._pixmap = QPixmap(self._source)
        else:
            self._pixmap = QPixmap()

    def set_source(self, path: str) -> None:
        path = str(path)
        if self._source == path:
            return
        self._source = path
        self._load_pixmap()
        self.update()
        self.notify_geometry_changed()

    def paint_content(self, painter: QPainter, rect):  # type: ignore[override]
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setOpacity(self._opacity)
        painter.fillRect(rect, self._background)
        if self._pixmap and not self._pixmap.isNull():
            target = self._target_rect(rect)
            painter.drawPixmap(target, self._pixmap)
        else:
            painter.setOpacity(1.0)
            painter.setPen(QColor(150, 150, 150))
            painter.drawRect(rect)
            painter.drawText(rect, Qt.AlignCenter, "Imagem")
        painter.restore()

    def _target_rect(self, rect):
        if self._pixmap.isNull():
            return rect
        pix_size = self._pixmap.size()
        if self._fit_mode == "stretch":
            return rect
        ratio_w = rect.width() / pix_size.width()
        ratio_h = rect.height() / pix_size.height()
        if self._fit_mode == "cover":
            scale = max(ratio_w, ratio_h)
        elif self._fit_mode == "actual":
            scale = 1.0
        else:  # contain
            scale = min(ratio_w, ratio_h)
        target_w = pix_size.width() * scale
        target_h = pix_size.height() * scale
        x = rect.center().x() - target_w / 2
        y = rect.center().y() - target_h / 2
        return QRectF(x, y, target_w, target_h)

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {
            "source": self._source,
            "fit_mode": self._fit_mode,
            "opacity": self._opacity,
            "background": self._background.name(),
        }

    def apply_serialized_data(self, data) -> None:
        if not isinstance(data, dict):
            return
        self._source = str(data.get("source", self._source))
        mode = data.get("fit_mode", self._fit_mode)
        if mode in self.FIT_MODES:
            self._fit_mode = mode
        self._opacity = max(0.1, min(1.0, float(data.get("opacity", self._opacity))))
        bg = data.get("background")
        if bg:
            self._background = QColor(bg)
        self._load_pixmap()
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def property_fields(self) -> Sequence[PropertyField]:
        return [
            PropertyField("source", "Arquivo", "path"),
            PropertyField("fit_mode", "Ajuste", "choice", options=self.FIT_MODES),
            PropertyField("opacity", "Opacidade", "float", minimum=0.1, maximum=1.0, step=0.05),
            PropertyField("background", "Fundo", "color"),
        ]

    def property_values(self) -> dict:
        return {
            "source": self._source,
            "fit_mode": self._fit_mode,
            "opacity": self._opacity,
            "background": self._background,
        }

    def set_property(self, name: str, value) -> None:
        if name == "source":
            self.set_source(str(value))
            return
        if name == "fit_mode" and value in self.FIT_MODES:
            self._fit_mode = str(value)
        elif name == "opacity":
            self._opacity = max(0.1, min(1.0, float(value)))
        elif name == "background":
            self._background = QColor(value)
        else:
            return
        self.update()
        self.notify_geometry_changed()
