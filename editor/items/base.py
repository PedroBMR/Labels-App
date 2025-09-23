"""Base classes and utilities for label editor items."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from qt_compat import (
    QAction,
    QColor,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QPainter,
    QPen,
    QPointF,
    QRectF,
    QSizeF,
    Qt,
    pyqtSignal,
)


@dataclass(frozen=True)
class PropertyField:
    """Description of an editable field shown in the property inspector."""

    name: str
    label: str
    field_type: str
    options: Sequence[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    multiline: bool = False
    placeholder: str | None = None


class BaseLabelItem(QGraphicsObject, ABC):
    """Interactive item that exposes resize, rotate and property editing."""

    propertiesChanged = pyqtSignal()

    HANDLE_SIZE = 6.0
    ROTATION_HANDLE_OFFSET = 28.0
    MIN_SIZE = 12.0

    def __init__(self, size: QSizeF | tuple[float, float] | None = None) -> None:
        super().__init__()
        if size is None:
            size = QSizeF(160.0, 60.0)
        if not isinstance(size, QSizeF):
            size = QSizeF(float(size[0]), float(size[1]))
        self._rect = QRectF(0.0, 0.0, size.width(), size.height())
        self._locked = False
        self._content_hidden = False
        self._interaction_mode: str | None = None
        self._resize_anchor = QPointF()
        self._rotation_start_vector = QPointF(1.0, 0.0)
        self._rotation_start_angle = 0.0
        self._undo_state: Any = None
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemSendsScenePositionChanges
        )
        self.setAcceptHoverEvents(True)

    # ------------------------------------------------------------------
    # Item metadata
    # ------------------------------------------------------------------
    def display_name(self) -> str:
        return self.__class__.__name__

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_size(self, width: float, height: float) -> None:
        width = max(self.MIN_SIZE, float(width))
        height = max(self.MIN_SIZE, float(height))
        if math.isclose(width, self._rect.width(), rel_tol=0.001, abs_tol=0.2) and math.isclose(
            height, self._rect.height(), rel_tol=0.001, abs_tol=0.2
        ):
            return
        self.prepareGeometryChange()
        self._rect = QRectF(0.0, 0.0, width, height)
        self.update()
        self.notify_geometry_changed()

    def set_rotation(self, angle: float) -> None:
        if math.isclose(self.rotation(), float(angle), abs_tol=0.1):
            self.setRotation(float(angle))
            return
        self.setRotation(float(angle))
        self.notify_geometry_changed()

    def boundingRect(self) -> QRectF:  # noqa: N802
        pad = self.HANDLE_SIZE + 2 if self.isSelected() else 2.0
        extra_top = self.ROTATION_HANDLE_OFFSET + self.HANDLE_SIZE if self.isSelected() else pad
        rect = QRectF(self._rect)
        rect = rect.adjusted(-pad, -extra_top, pad, pad)
        return rect

    # ------------------------------------------------------------------
    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        self.setFlag(QGraphicsItem.ItemIsMovable, not locked)

    def is_locked(self) -> bool:
        return self._locked

    def set_content_hidden(self, hidden: bool) -> None:
        self._content_hidden = bool(hidden)
        self.setOpacity(0.35 if hidden else 1.0)
        self.update()

    def is_content_hidden(self) -> bool:
        return self._content_hidden

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:  # noqa: D401
        menu = QMenu()
        lock_action = QAction("Desbloquear" if self._locked else "Bloquear", menu)
        lock_action.triggered.connect(lambda: self.set_locked(not self._locked))
        menu.addAction(lock_action)

        hide_action = QAction("Mostrar" if self._content_hidden else "Ocultar", menu)
        hide_action.triggered.connect(lambda: self.set_content_hidden(not self._content_hidden))
        menu.addAction(hide_action)

        execute = getattr(menu, "exec", None)
        if execute is None:
            execute = menu.exec_  # type: ignore[attr-defined]
        execute(event.screenPos())

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------
    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: D401
        if self._locked:
            self.unsetCursor()
            return
        handle = self._handle_at(event.pos())
        if handle:
            cursor = {
                "top-left": Qt.SizeFDiagCursor,
                "bottom-right": Qt.SizeFDiagCursor,
                "top-right": Qt.SizeBDiagCursor,
                "bottom-left": Qt.SizeBDiagCursor,
            }.get(handle, Qt.SizeAllCursor)
            self.setCursor(cursor)
            return
        if self._rotation_handle_rect().contains(event.pos()):
            self.setCursor(Qt.CrossCursor)
            return
        if self.isSelected():
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:  # noqa: D401
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401
        if self._locked and event.button() == Qt.LeftButton:
            event.ignore()
            return
        scene = self.scene()
        undo_state = None
        if scene is not None:
            from ..scene import LabelScene

            if isinstance(scene, LabelScene):
                undo_state = scene.capture_item_state(self)
        if event.button() == Qt.LeftButton:
            handle = self._handle_at(event.pos())
            if handle and not self._locked:
                self._interaction_mode = "resize"
                self._resize_anchor = self._anchor_for_handle(handle)
                self._undo_state = (undo_state, "Redimensionar")
                event.accept()
                return
            if self._rotation_handle_rect().contains(event.pos()) and not self._locked:
                self._interaction_mode = "rotate"
                center = self._rect.center()
                self._rotation_start_vector = event.pos() - center
                if self._rotation_start_vector.manhattanLength() < 0.001:
                    self._rotation_start_vector = QPointF(1.0, 0.0)
                self._rotation_start_angle = self.rotation()
                self._undo_state = (undo_state, "Rotacionar")
                event.accept()
                return
            self._interaction_mode = "move"
            self._undo_state = (undo_state, "Mover")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401
        if self._interaction_mode == "resize":
            self._perform_resize(event.pos())
            event.accept()
            return
        if self._interaction_mode == "rotate":
            self._perform_rotate(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: D401
        if self._interaction_mode and event.button() == Qt.LeftButton:
            self._commit_undo()
            self._interaction_mode = None
            self._undo_state = None
            from ..scene import LabelScene

            scene = self.scene()
            if isinstance(scene, LabelScene):
                scene.clear_alignment_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any):  # noqa: D401
        from ..scene import LabelScene

        scene = self.scene()
        if change == QGraphicsItem.ItemPositionChange and isinstance(scene, LabelScene):
            if scene.is_restoring:
                return super().itemChange(change, value)
            if self._interaction_mode == "move" and isinstance(value, QPointF):
                snapped = scene.snap_point(value)
                scene.update_alignment_guides(self, snapped)
                return super().itemChange(change, snapped)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            if isinstance(scene, LabelScene) and not scene.is_restoring:
                scene.clear_alignment_guides()
            self.notify_geometry_changed()
        elif change in (
            QGraphicsItem.ItemRotationHasChanged,
            QGraphicsItem.ItemScaleHasChanged,
        ):
            self.notify_geometry_changed()
        return result

    # ------------------------------------------------------------------
    def _perform_resize(self, pos: QPointF) -> None:
        rect = QRectF(self._resize_anchor, pos).normalized()
        width = max(rect.width(), self.MIN_SIZE)
        height = max(rect.height(), self.MIN_SIZE)
        delta = rect.topLeft()
        self.prepareGeometryChange()
        self._rect = QRectF(0.0, 0.0, width, height)
        if not delta.isNull():
            self.setPos(self.pos() + delta)
        self.update()
        self.notify_geometry_changed()
        from ..scene import LabelScene

        scene = self.scene()
        if isinstance(scene, LabelScene):
            scene.update_alignment_guides(self)

    def _perform_rotate(self, pos: QPointF) -> None:
        center = self._rect.center()
        current_vector = pos - center
        if current_vector.manhattanLength() < 0.001:
            return
        base_angle = math.degrees(math.atan2(self._rotation_start_vector.y(), self._rotation_start_vector.x()))
        current_angle = math.degrees(math.atan2(current_vector.y(), current_vector.x()))
        delta = current_angle - base_angle
        self.setRotation(self._rotation_start_angle + delta)
        from ..scene import LabelScene

        scene = self.scene()
        if isinstance(scene, LabelScene):
            scene.update_alignment_guides(self)

    def _handle_rects(self) -> dict[str, QRectF]:
        rect = self._rect
        size = self.HANDLE_SIZE
        return {
            "top-left": QRectF(rect.topLeft() - QPointF(size / 2, size / 2), QSizeF(size, size)),
            "top-right": QRectF(rect.topRight() - QPointF(size / 2, size / 2), QSizeF(size, size)),
            "bottom-left": QRectF(rect.bottomLeft() - QPointF(size / 2, size / 2), QSizeF(size, size)),
            "bottom-right": QRectF(rect.bottomRight() - QPointF(size / 2, size / 2), QSizeF(size, size)),
        }

    def _rotation_handle_rect(self) -> QRectF:
        size = self.HANDLE_SIZE * 1.2
        top = self._rect.top() - self.ROTATION_HANDLE_OFFSET
        center_x = self._rect.center().x()
        return QRectF(
            QPointF(center_x - size / 2, top - size / 2),
            QSizeF(size, size),
        )

    def _handle_at(self, pos: QPointF) -> str | None:
        for key, rect in self._handle_rects().items():
            if rect.contains(pos):
                return key
        return None

    def _anchor_for_handle(self, handle: str) -> QPointF:
        if handle == "top-left":
            return self._rect.bottomRight()
        if handle == "top-right":
            return self._rect.bottomLeft()
        if handle == "bottom-left":
            return self._rect.topRight()
        return self._rect.topLeft()

    def _commit_undo(self) -> None:
        if not isinstance(self._undo_state, tuple):
            return
        before, description = self._undo_state
        if before is None:
            return
        from ..scene import LabelScene

        scene = self.scene()
        if isinstance(scene, LabelScene):
            after = scene.capture_item_state(self)
            scene.push_state(self, before, after, description)

    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D401
        if not self._content_hidden:
            self.paint_content(painter, self._rect)
        if self.isSelected():
            self._paint_overlay(painter)

    def _paint_overlay(self, painter: QPainter) -> None:
        pen = QPen(QColor(10, 132, 255), 0)
        pen.setStyle(Qt.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)
        handle_brush = QColor(10, 132, 255)
        for rect in self._handle_rects().values():
            painter.fillRect(rect, handle_brush)
        painter.setBrush(handle_brush)
        painter.drawEllipse(self._rotation_handle_rect())
        painter.restore()

    # ------------------------------------------------------------------
    def notify_geometry_changed(self) -> None:
        if not self.signalsBlocked():
            self.propertiesChanged.emit()

    # ------------------------------------------------------------------
    def serialize_data(self) -> dict:
        return {}

    def apply_serialized_data(self, data: Mapping[str, Any]) -> None:
        del data  # unused in base class

    # ------------------------------------------------------------------
    @abstractmethod
    def paint_content(self, painter: QPainter, rect: QRectF) -> None:
        raise NotImplementedError

    def property_fields(self) -> Sequence[PropertyField]:
        return []

    def property_values(self) -> Dict[str, Any]:
        return {}

    def set_property(self, name: str, value: Any) -> None:
        del name, value
*** End Patch
