"""Text item for the label editor."""
from __future__ import annotations

from typing import Sequence

from qt_compat import QColor, QFont, QFontDatabase, QPainter, Qt

from .base import BaseLabelItem, PropertyField


def _default_font_family() -> str:
    db = QFontDatabase()
    families = db.families()
    return families[0] if families else "Sans Serif"


class TextLabelItem(BaseLabelItem):
    """Simple text item with font and alignment controls."""

    def __init__(
        self,
        text: str = "",
        size: tuple[float, float] | None = None,
        font_family: str | None = None,
        font_size: float = 14.0,
        color: QColor | None = None,
        alignment: str = "left",
        bold: bool = False,
        italic: bool = False,
    ) -> None:
        super().__init__(size)
        self._text = text
        self._font_family = font_family or _default_font_family()
        self._font_size = float(font_size)
        self._color = QColor(color or QColor(20, 20, 20))
        self._alignment = alignment
        self._bold = bool(bold)
        self._italic = bool(italic)

    # ------------------------------------------------------------------
    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        if self._text == text:
            return
        self._text = text
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def _build_font(self) -> QFont:
        font = QFont(self._font_family, max(1, int(round(self._font_size))))
        font.setBold(self._bold)
        font.setItalic(self._italic)
        return font

    def _alignment_flag(self) -> int:
        mapping = {
            "center": Qt.AlignHCenter | Qt.AlignVCenter,
            "right": Qt.AlignRight | Qt.AlignVCenter,
        }
        return mapping.get(self._alignment, Qt.AlignLeft | Qt.AlignVCenter)

    def paint_content(self, painter: QPainter, rect):  # type: ignore[override]
        painter.save()
        painter.setPen(self._color)
        painter.setFont(self._build_font())
        flags = self._alignment_flag() | Qt.TextWordWrap
        painter.drawText(rect, flags, self._text)
        painter.restore()

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {
            "text": self._text,
            "font_family": self._font_family,
            "font_size": self._font_size,
            "color": self._color.name(),
            "alignment": self._alignment,
            "bold": self._bold,
            "italic": self._italic,
        }

    def apply_serialized_data(self, data) -> None:
        if not isinstance(data, dict):
            return
        self._text = str(data.get("text", self._text))
        self._font_family = str(data.get("font_family", self._font_family))
        self._font_size = float(data.get("font_size", self._font_size))
        self._alignment = str(data.get("alignment", self._alignment))
        self._bold = bool(data.get("bold", self._bold))
        self._italic = bool(data.get("italic", self._italic))
        color = data.get("color")
        if color:
            self._color = QColor(color)
        self.update()
        self.notify_geometry_changed()

    # ------------------------------------------------------------------
    def property_fields(self) -> Sequence[PropertyField]:
        return [
            PropertyField("text", "Texto", "multiline", multiline=True),
            PropertyField("font_family", "Fonte", "font"),
            PropertyField("font_size", "Tamanho", "float", minimum=4.0, maximum=240.0, step=0.5),
            PropertyField("alignment", "Alinhamento", "choice", options=["left", "center", "right"]),
            PropertyField("bold", "Negrito", "bool"),
            PropertyField("italic", "Itálico", "bool"),
            PropertyField("color", "Cor", "color"),
        ]

    def property_values(self) -> dict:
        return {
            "text": self._text,
            "font_family": self._font_family,
            "font_size": self._font_size,
            "alignment": self._alignment,
            "bold": self._bold,
            "italic": self._italic,
            "color": self._color,
        }

    def set_property(self, name: str, value) -> None:
        if name == "text":
            self.set_text(str(value))
            return
        if name == "font_family":
            self._font_family = str(value)
        elif name == "font_size":
            self._font_size = float(value)
        elif name == "alignment":
            self._alignment = str(value)
        elif name == "bold":
            self._bold = bool(value)
        elif name == "italic":
            self._italic = bool(value)
        elif name == "color":
            self._color = QColor(value)
        else:
            return
        self.update()
        self.notify_geometry_changed()
