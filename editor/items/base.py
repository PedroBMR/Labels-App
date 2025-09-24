"""Interactive graphics items used by the label editor."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from PIL.ImageQt import ImageQt

from qt_compat import (
    QColor,
    QCursor,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QKeyEvent,
    QLineF,
    QPainter,
    QPen,
    QPixmap,
    QPointF,
    QRectF,
    Qt,
    pyqtSignal,
)
from render.preview import render_element_image

if False:  # pragma: no cover - typing only
    from .scene import LabelScene  # noqa: F401

HANDLE_SIZE = 8.0


@dataclass(frozen=True)
class GeometryState:
    """Capture the geometry of an item for undo/redo operations."""

    position: QPointF
    rect: QRectF
    rotation: float


class GraphicsElementItem(QGraphicsObject):
    """Base class for scene items representing template elements."""

    changed = pyqtSignal()
    geometryCommitted = pyqtSignal(object, GeometryState, GeometryState)
    propertyChanged = pyqtSignal(object, str, object)

    def __init__(self, element: Mapping[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._element: dict[str, Any] = {"type": "text"}
        self._pixmap = QPixmap()
        self._rect = QRectF(0.0, 0.0, 20.0, 20.0)
        self._locked = False
        self._initial_state: GeometryState | None = None
        self._resize_anchor: str | None = None
        self._rotating = False
        self.setFlags(
            QGraphicsObject.ItemIsSelectable
            | QGraphicsObject.ItemIsMovable
            | QGraphicsObject.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        if element:
            self.apply_element(element)

    # ------------------------------------------------------------------
    def scene(self) -> "LabelScene":  # type: ignore[override]
        return super().scene()  # type: ignore[return-value]

    # ------------------------------------------------------------------
    @property
    def element(self) -> dict[str, Any]:
        return dict(self._element)

    def apply_element(self, element: Mapping[str, Any]) -> None:
        data = dict(element)
        element_type = str(data.get("type", self._element.get("type", "text")))
        data["type"] = element_type
        self._element = data
        self._locked = bool(data.get("locked", False))
        self.setVisible(not bool(data.get("hidden", False)))
        self.setFlag(QGraphicsObject.ItemIsMovable, not self._locked)
        self._update_geometry_from_element()
        self._update_pixmap()
        self.changed.emit()

    # ------------------------------------------------------------------
    def _update_geometry_from_element(self) -> None:
        scene = self.scene()
        if not scene:
            return
        rect = scene.element_rect(self._element)
        self.prepareGeometryChange()
        self._rect = QRectF(0.0, 0.0, rect.width(), rect.height())
        self.setPos(rect.topLeft())
        rotation = float(self._element.get("rotation", 0.0))
        self.setRotation(rotation)
        self.setTransformOriginPoint(self._rect.center())

    def _update_pixmap(self) -> None:
        scene = self.scene()
        if not scene:
            return
        context = scene.preview_context()
        page = scene.page
        calibration = scene.calibration
        result = render_element_image(
            self._element,
            context,
            page,
            calibration=calibration,
        )
        if result:
            image, width_px, height_px = result
            if width_px <= 0 or height_px <= 0:
                return
            self.prepareGeometryChange()
            self._rect = QRectF(0.0, 0.0, width_px, height_px)
            self.setTransformOriginPoint(self._rect.center())
            self._pixmap = QPixmap.fromImage(ImageQt(image))
        else:
            self._pixmap = QPixmap()

    # ------------------------------------------------------------------
    def boundingRect(self) -> QRectF:  # noqa: D401 - Qt API
        return self._rect.adjusted(-HANDLE_SIZE, -HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE)

    def shapeRect(self) -> QRectF:
        return QRectF(self._rect)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D401 - Qt API
        if not self._pixmap.isNull():
            painter.drawPixmap(
                self._rect,
                self._pixmap,
                QRectF(0, 0, self._pixmap.width(), self._pixmap.height()),
            )
        if self.isSelected():
            pen = QPen(QColor(0, 120, 215))
            pen.setStyle(Qt.DashLine)
            pen.setWidth(0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect)
            painter.setBrush(QColor(0, 120, 215))
            for handle in self._handle_rects():
                painter.drawRect(handle)
            painter.setBrush(QColor(255, 128, 0))
            painter.drawEllipse(self._rotation_handle())

    # ------------------------------------------------------------------
    def _handle_rects(self) -> list[QRectF]:
        size = HANDLE_SIZE
        rect = self._rect
        handles = [
            QRectF(rect.left() - size, rect.top() - size, size, size),
            QRectF(rect.center().x() - size / 2, rect.top() - size, size, size),
            QRectF(rect.right(), rect.top() - size, size, size),
            QRectF(rect.right(), rect.center().y() - size / 2, size, size),
            QRectF(rect.right(), rect.bottom(), size, size),
            QRectF(rect.center().x() - size / 2, rect.bottom(), size, size),
            QRectF(rect.left() - size, rect.bottom(), size, size),
            QRectF(rect.left() - size, rect.center().y() - size / 2, size, size),
        ]
        return handles

    def _rotation_handle(self) -> QRectF:
        rect = self._rect
        size = HANDLE_SIZE
        return QRectF(rect.center().x() - size / 2, rect.top() - size * 2.5, size, size)

    def _handle_at_pos(self, pos: QPointF) -> str | None:
        for index, handle in enumerate(self._handle_rects()):
            if handle.contains(pos):
                return [
                    "top-left",
                    "top",
                    "top-right",
                    "right",
                    "bottom-right",
                    "bottom",
                    "bottom-left",
                    "left",
                ][index]
        if self._rotation_handle().contains(pos):
            return "rotate"
        return None

    # ------------------------------------------------------------------
    def hoverMoveEvent(self, event) -> None:  # noqa: D401 - Qt API
        handle = self._handle_at_pos(event.pos())
        cursor = Qt.ArrowCursor
        if handle == "top" or handle == "bottom":
            cursor = Qt.SizeVerCursor
        elif handle == "left" or handle == "right":
            cursor = Qt.SizeHorCursor
        elif handle in {"top-left", "bottom-right"}:
            cursor = Qt.SizeFDiagCursor
        elif handle in {"top-right", "bottom-left"}:
            cursor = Qt.SizeBDiagCursor
        elif handle == "rotate":
            cursor = Qt.OpenHandCursor
        self.setCursor(QCursor(cursor))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: D401 - Qt API
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401 - Qt API
        self._initial_state = self.current_state()
        handle = self._handle_at_pos(event.pos())
        self._resize_anchor = handle if handle and handle != "rotate" else None
        self._rotating = handle == "rotate"
        if self._rotating:
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401 - Qt API
        if self._rotating:
            self._apply_rotation(event.pos())
            return
        if self._resize_anchor:
            self._apply_resize(event.pos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401 - Qt API
        super().mouseReleaseEvent(event)
        if self._rotating:
            self.setCursor(Qt.OpenHandCursor)
        self._rotating = False
        self._resize_anchor = None
        if self._initial_state is not None:
            new_state = self.current_state()
            if self.scene():
                self.geometryCommitted.emit(self, self._initial_state, new_state)
            self._initial_state = None

    # ------------------------------------------------------------------
    def _apply_rotation(self, pos: QPointF) -> None:
        center = self.transformOriginPoint()
        line = QLineF(center, pos)
        angle = 360 - line.angle()
        scene = self.scene()
        if scene:
            angle = scene.snap_rotation(angle)
        self.setRotation(angle)
        self._element["rotation"] = angle
        self._update_element_geometry()
        self.changed.emit()

    def _apply_resize(self, pos: QPointF) -> None:
        rect = QRectF(self._rect)
        anchor = self._resize_anchor
        min_size = 5.0
        if anchor in {"top-left", "left", "bottom-left"}:
            new_left = min(pos.x(), rect.right() - min_size)
            rect.setLeft(new_left)
        if anchor in {"top-right", "right", "bottom-right"}:
            new_right = max(pos.x(), rect.left() + min_size)
            rect.setRight(new_right)
        if anchor in {"top-left", "top", "top-right"}:
            new_top = min(pos.y(), rect.bottom() - min_size)
            rect.setTop(new_top)
        if anchor in {"bottom-left", "bottom", "bottom-right"}:
            new_bottom = max(pos.y(), rect.top() + min_size)
            rect.setBottom(new_bottom)

        scene = self.scene()
        rect = scene.snap_rect(rect, self) if scene else rect
        self.prepareGeometryChange()
        self._rect = rect
        self.setTransformOriginPoint(self._rect.center())
        if anchor in {"top", "top-left", "top-right"}:
            delta_y = rect.top()
            self.setY(self.y() + delta_y)
        if anchor in {"left", "top-left", "bottom-left"}:
            delta_x = rect.left()
            self.setX(self.x() + delta_x)
        self._rect.moveTo(0, 0)
        self._update_element_geometry()
        self._update_pixmap()
        self.changed.emit()

    # ------------------------------------------------------------------
    def current_state(self) -> GeometryState:
        return GeometryState(self.pos(), QRectF(self._rect), float(self.rotation()))

    def restore_state(self, state: GeometryState) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(state.rect)
        self.setPos(state.position)
        self.setRotation(state.rotation)
        self.setTransformOriginPoint(self._rect.center())
        self._update_element_geometry()
        self._update_pixmap()
        self.changed.emit()

    # ------------------------------------------------------------------
    def itemChange(self, change, value):  # noqa: D401 - Qt API
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene():
            self._update_geometry_from_element()
            self._update_pixmap()
        if change == QGraphicsObject.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            snapped = self.scene().snap_point(self, new_pos)
            self._element["x_mm"] = self.scene().to_mm_x(snapped.x())
            self._element["y_mm"] = self.scene().to_mm_y(snapped.y())
            return snapped
        if change == QGraphicsObject.ItemSelectedChange:
            if not value and self.scene():
                self.scene().clear_guides()
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: D401 - Qt API
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            scene = self.scene()
            if scene:
                scene.delete_item(self)
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def update_property(self, name: str, value: Any) -> None:
        self._element[name] = copy.deepcopy(value)
        if name in {"x_mm", "y_mm", "width_mm", "height_mm", "rotation"}:
            self._update_geometry_from_element()
        self._update_pixmap()
        self.propertyChanged.emit(self, name, value)
        self.changed.emit()

    def lock(self, state: bool) -> None:
        self._locked = state
        self._element["locked"] = state
        self.setFlag(QGraphicsObject.ItemIsMovable, not state)

    def set_hidden(self, hidden: bool) -> None:
        self._element["hidden"] = hidden
        self.setVisible(not hidden)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = dict(self._element)
        scene = self.scene()
        rect = self.mapRectToScene(self._rect)
        data["x_mm"] = scene.to_mm_x(rect.left()) if scene else rect.left()
        data["y_mm"] = scene.to_mm_y(rect.top()) if scene else rect.top()
        data["width_mm"] = scene.to_mm_x(rect.width()) if scene else rect.width()
        data["height_mm"] = scene.to_mm_y(rect.height()) if scene else rect.height()
        data["rotation"] = float(self.rotation())
        return data

    def _update_element_geometry(self) -> None:
        scene = self.scene()
        if not scene:
            return
        rect = self.mapRectToScene(self._rect)
        self._element["x_mm"] = scene.to_mm_x(rect.left())
        self._element["y_mm"] = scene.to_mm_y(rect.top())
        self._element["width_mm"] = scene.to_mm_x(rect.width())
        self._element["height_mm"] = scene.to_mm_y(rect.height())
        self._element["rotation"] = float(self.rotation())


def iter_element_items(
    items: Iterable[QGraphicsObject],
) -> Iterable[GraphicsElementItem]:
    for item in items:
        if isinstance(item, GraphicsElementItem):
            yield item
