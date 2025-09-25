"""Editable text graphics item used by the editor."""

from __future__ import annotations

from typing import Any, Mapping

from qt_compat import (
    QColor,
    QFocusEvent,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QKeyEvent,
    QPointF,
    QRectF,
    Qt,
    pyqtSignal,
)

from .base import GeometryState

__all__ = ["EditableTextItem", "TextGraphicsItem"]


class EditableTextItem(QGraphicsTextItem):
    """Text item that toggles edit mode on demand."""

    editingStarted = pyqtSignal()
    editingFinished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._locked = False
        self._editing = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

    # ------------------------------------------------------------------
    def is_editing(self) -> bool:
        return self._editing

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.setFlag(QGraphicsItem.ItemIsMovable, not locked)
        if locked and self._editing:
            self.clearFocus()
            self._finish_editing()

    def lock(self, state: bool) -> None:
        self.set_locked(state)
        if hasattr(self, "_element"):
            self._element["locked"] = state

    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):  # noqa: D401 - Qt API
        if self._locked:
            event.ignore()
            return
        if not self._editing:
            self._begin_editing()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: D401 - Qt API
        if self._editing and event.key() in {
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Escape,
        }:
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: D401 - Qt API
        super().focusOutEvent(event)
        if self._editing:
            self._finish_editing()

    # ------------------------------------------------------------------
    def _begin_editing(self) -> None:
        self._editing = True
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        self.editingStarted.emit()

    def _finish_editing(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.editingFinished.emit()


class TextGraphicsItem(EditableTextItem):
    """Interactive text item mirroring the :class:`GraphicsElementItem` API."""

    changed = pyqtSignal()
    geometryCommitted = pyqtSignal(object, GeometryState, GeometryState)
    propertyChanged = pyqtSignal(object, str, object)

    def __init__(self, element: Mapping[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._element: dict[str, Any] = {"type": "text", "content": "New Text"}
        self._initial_state: GeometryState | None = None
        self.setDefaultTextColor(QColor(0, 0, 0))
        self.document().contentsChanged.connect(self._on_content_changed)
        if element:
            self.apply_element(element)
        else:
            self.setPlainText("New Text")

    # ------------------------------------------------------------------
    def scene(self):  # type: ignore[override]
        return super().scene()  # type: ignore[return-value]

    # ------------------------------------------------------------------
    @property
    def element(self) -> dict[str, Any]:
        return dict(self._element)

    # ------------------------------------------------------------------
    def apply_element(self, element: Mapping[str, Any]) -> None:
        data = dict(element)
        data.setdefault("type", "text")
        data.setdefault("content", "New Text")
        self._element = data
        self.set_locked(bool(data.get("locked", False)))
        self.setVisible(not bool(data.get("hidden", False)))
        self.setPlainText(str(data.get("content", "New Text")))
        font_raw = data.get("font", {})
        font_data = dict(font_raw) if isinstance(font_raw, Mapping) else {}
        font = self.font()
        size = font_data.get("size")
        if size:
            font.setPointSizeF(float(size))
        family = font_data.get("family")
        if family:
            font.setFamily(str(family))
        font.setBold(bool(font_data.get("bold", False)))
        font.setItalic(bool(font_data.get("italic", False)))
        self.setFont(font)
        align = str(data.get("align", font_data.get("align", "left")))
        self._element["align"] = align
        option = self.document().defaultTextOption()
        if align == "center":
            option.setAlignment(Qt.AlignHCenter)
        elif align == "right":
            option.setAlignment(Qt.AlignRight)
        else:
            option.setAlignment(Qt.AlignLeft)
        self.document().setDefaultTextOption(option)
        self._update_geometry_from_element()
        self.changed.emit()

    def _update_geometry_from_element(self) -> None:
        scene = self.scene()
        if not scene:
            return
        rect = scene.element_rect(self._element)
        self.prepareGeometryChange()
        self.setTextWidth(max(1.0, rect.width()))
        self.setRotation(float(self._element.get("rotation", 0.0)))
        self.setTransformOriginPoint(self.boundingRect().center())
        self.setPos(rect.topLeft())

    def _update_element_geometry(self) -> None:
        scene = self.scene()
        if not scene:
            return
        rect = self.mapRectToScene(self.boundingRect())
        self._element["x_mm"] = scene.to_mm_x(rect.left())
        self._element["y_mm"] = scene.to_mm_y(rect.top())
        self._element["width_mm"] = scene.to_mm_x(rect.width())
        self._element["height_mm"] = scene.to_mm_y(rect.height())
        self._element["rotation"] = float(self.rotation())

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401 - Qt API
        self._initial_state = self.current_state()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401 - Qt API
        super().mouseReleaseEvent(event)
        if self._initial_state is not None:
            new_state = self.current_state()
            if self.scene():
                self.geometryCommitted.emit(self, self._initial_state, new_state)
            self._initial_state = None

    # ------------------------------------------------------------------
    def itemChange(self, change, value):  # noqa: D401 - Qt API
        if change == QGraphicsItem.ItemSelectedChange and not value and self.scene():
            self.scene().clear_guides()
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            snapped = self.scene().snap_point(self, QPointF(new_pos))
            self._element["x_mm"] = self.scene().to_mm_x(snapped.x())
            self._element["y_mm"] = self.scene().to_mm_y(snapped.y())
            return snapped
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._update_element_geometry()
            self.changed.emit()
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    def current_state(self) -> GeometryState:
        return GeometryState(
            self.pos(),
            QRectF(self.boundingRect()),
            float(self.rotation()),
        )

    def restore_state(self, state: GeometryState) -> None:
        self.prepareGeometryChange()
        self.setPos(state.position)
        self.setRotation(state.rotation)
        self.setTransformOriginPoint(self.boundingRect().center())
        self._update_element_geometry()
        self.changed.emit()

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        self._update_element_geometry()
        data = dict(self._element)
        data["content"] = self.toPlainText()
        data.setdefault("font", {})
        data["font"]["size"] = self.font().pointSizeF()
        data["font"]["family"] = self.font().family()
        data["font"]["bold"] = self.font().bold()
        data["font"]["italic"] = self.font().italic()
        data["align"] = self._element.get("align", "left")
        return data

    # ------------------------------------------------------------------
    def update_property(self, name: str, value: Any) -> None:
        self._element[name] = value
        if name == "content":
            self.setPlainText(str(value))
        elif name == "font":
            self._apply_font(value)
        elif name == "align":
            self._element["align"] = str(value)
            option = self.document().defaultTextOption()
            align = str(value)
            if align == "center":
                option.setAlignment(Qt.AlignHCenter)
            elif align == "right":
                option.setAlignment(Qt.AlignRight)
            else:
                option.setAlignment(Qt.AlignLeft)
            self.document().setDefaultTextOption(option)
        elif name in {"x_mm", "y_mm", "width_mm", "height_mm", "rotation"}:
            self._update_geometry_from_element()
        self.propertyChanged.emit(self, name, value)
        self.changed.emit()

    def _apply_font(self, value: Mapping[str, Any]) -> None:
        font = self.font()
        if "size" in value:
            font.setPointSizeF(float(value["size"]))
        if "family" in value:
            font.setFamily(str(value["family"]))
        font.setBold(bool(value.get("bold", font.bold())))
        font.setItalic(bool(value.get("italic", font.italic())))
        self.setFont(font)

    def lock(self, state: bool) -> None:
        self._element["locked"] = state
        self.set_locked(state)

    def set_hidden(self, hidden: bool) -> None:
        self._element["hidden"] = hidden
        self.setVisible(not hidden)

    # ------------------------------------------------------------------
    def _on_content_changed(self) -> None:
        self._element["content"] = self.toPlainText()
        self._update_element_geometry()
        self.changed.emit()

    # ------------------------------------------------------------------
    def shapeRect(self) -> QRectF:
        return QRectF(self.boundingRect())

