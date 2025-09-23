"""Graphics scene and view helpers for the label editor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, TYPE_CHECKING

from qt_compat import (
    QColor,
    QCursor,
    QBrush,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QLineF,
    QPoint,
    QPointF,
    QRectF,
    QPen,
    QPainter,
    QPalette,
    QEvent,
    QWidget,
    Qt,
    QWheelEvent,
    QMouseEvent,
    QResizeEvent,
    QScrollBar,
    pyqtSignal,
)
from qt_compat import QUndoCommand, QUndoStack

if TYPE_CHECKING:  # pragma: no cover - used only for typing
    from .items.base import BaseLabelItem


@dataclass
class _ItemState:
    pos: QPointF
    width: float
    height: float
    rotation: float
    data: dict


class _ItemStateCommand(QUndoCommand):
    """Undo command that restores a single item's state."""

    def __init__(
        self,
        item: "BaseLabelItem",
        before: _ItemState,
        after: _ItemState,
        text: str,
    ) -> None:
        super().__init__(text)
        self._item = item
        self._before = before
        self._after = after

    def undo(self) -> None:  # noqa: D401 - Qt API
        scene = self._item.scene()
        if isinstance(scene, LabelScene):
            scene._restore_item_state(self._item, self._before)

    def redo(self) -> None:  # noqa: D401 - Qt API
        scene = self._item.scene()
        if isinstance(scene, LabelScene):
            scene._restore_item_state(self._item, self._after)


class _MultiItemStateCommand(QUndoCommand):
    """Undo command that restores multiple items together."""

    def __init__(
        self,
        items: Sequence["BaseLabelItem"],
        before: Sequence[_ItemState],
        after: Sequence[_ItemState],
        text: str,
    ) -> None:
        super().__init__(text)
        self._items = list(items)
        self._before = list(before)
        self._after = list(after)

    def undo(self) -> None:  # noqa: D401 - Qt API
        if not self._items:
            return
        scene = self._items[0].scene()
        if isinstance(scene, LabelScene):
            for item, state in zip(self._items, self._before, strict=False):
                scene._restore_item_state(item, state)

    def redo(self) -> None:  # noqa: D401 - Qt API
        if not self._items:
            return
        scene = self._items[0].scene()
        if isinstance(scene, LabelScene):
            for item, state in zip(self._items, self._after, strict=False):
                scene._restore_item_state(item, state)


class LabelScene(QGraphicsScene):
    """Graphics scene that understands label templates measured in millimetres."""

    templateChanged = pyqtSignal()

    def __init__(self, dpi: float = 203.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dpi = dpi
        self._dots_per_mm = dpi / 25.4
        self._grid_mm = 1.0
        self._grid_visible = True
        self._snap_to_grid = True
        self._guide_pen = QPen(QColor(255, 85, 0, 200), 0, Qt.DashLine)
        self._guide_items: list[QGraphicsLineItem] = []
        self._undo_stack: QUndoStack | None = None
        self._restoring = False
        self._background_brush = QBrush(QColor(35, 35, 35))
        self._label_brush = QBrush(QColor(250, 250, 250))
        self.setItemIndexMethod(QGraphicsScene.NoIndex)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    @property
    def dpi(self) -> float:
        return self._dpi

    def set_dpi(self, dpi: float) -> None:
        self._dpi = dpi
        self._dots_per_mm = dpi / 25.4
        self.update()
        self.templateChanged.emit()

    def mm_to_dots(self, value: float) -> float:
        return value * self._dots_per_mm

    def dots_to_mm(self, value: float) -> float:
        if self._dots_per_mm == 0:
            return value
        return value / self._dots_per_mm

    # ------------------------------------------------------------------
    # Template management
    # ------------------------------------------------------------------
    def set_template_rect(self, width_mm: float, height_mm: float) -> None:
        rect = QRectF(0.0, 0.0, self.mm_to_dots(width_mm), self.mm_to_dots(height_mm))
        self.setSceneRect(rect)
        self.templateChanged.emit()

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------
    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        self.update()

    def is_grid_visible(self) -> bool:
        return self._grid_visible

    def set_grid_mm(self, size_mm: float) -> None:
        self._grid_mm = max(0.1, float(size_mm))
        self.update()

    def grid_size_dots(self) -> float:
        return self.mm_to_dots(self._grid_mm)

    def set_snap_to_grid(self, enabled: bool) -> None:
        self._snap_to_grid = enabled

    def snap_point(self, point: QPointF) -> QPointF:
        if not self._snap_to_grid:
            return point
        grid = self.grid_size_dots()
        if grid <= 0:
            return point
        return QPointF(
            round(point.x() / grid) * grid,
            round(point.y() / grid) * grid,
        )

    # ------------------------------------------------------------------
    # Undo helpers
    # ------------------------------------------------------------------
    def set_undo_stack(self, stack: QUndoStack | None) -> None:
        self._undo_stack = stack

    def undo_stack(self) -> QUndoStack | None:
        return self._undo_stack

    def capture_item_state(self, item: "BaseLabelItem") -> _ItemState:
        rect = item.rect()
        return _ItemState(
            pos=item.pos(),
            width=rect.width(),
            height=rect.height(),
            rotation=item.rotation(),
            data=item.serialize_data(),
        )

    def push_state(self, item: "BaseLabelItem", before: _ItemState, after: _ItemState, text: str) -> None:
        if self._undo_stack is None:
            return
        if before == after:
            return
        command = _ItemStateCommand(item, before, after, text)
        self._undo_stack.push(command)

    def push_multi_state(
        self,
        items: Sequence["BaseLabelItem"],
        before: Sequence[_ItemState],
        after: Sequence[_ItemState],
        text: str,
    ) -> None:
        if self._undo_stack is None:
            return
        if list(before) == list(after):
            return
        command = _MultiItemStateCommand(items, before, after, text)
        self._undo_stack.push(command)

    def _restore_item_state(self, item: "BaseLabelItem", state: _ItemState) -> None:
        self._restoring = True
        try:
            item.blockSignals(True)
            item.set_rotation(state.rotation)
            item.set_size(state.width, state.height)
            item.setPos(state.pos)
            item.apply_serialized_data(state.data)
        finally:
            item.blockSignals(False)
            self._restoring = False
        item.notify_geometry_changed()

    # ------------------------------------------------------------------
    # Guide helpers
    # ------------------------------------------------------------------
    def update_alignment_guides(self, item: "BaseLabelItem", position: QPointF | None = None) -> None:
        if self._restoring:
            return
        rect = item.mapToScene(item.boundingRect()).boundingRect()
        if position is not None:
            rect.moveTo(position)
        lines: list[QLineF] = []
        tolerance = max(2.0, self.mm_to_dots(0.25))
        scene_rect = self.sceneRect()

        from .items.base import BaseLabelItem  # local import to avoid cycle

        for other in self.items():
            if other is item or not isinstance(other, BaseLabelItem):
                continue
            if not other.isVisible():
                continue
            other_rect = other.mapToScene(other.boundingRect()).boundingRect()
            if abs(rect.left() - other_rect.left()) <= tolerance:
                x = other_rect.left()
                lines.append(QLineF(x, scene_rect.top(), x, scene_rect.bottom()))
            if abs(rect.right() - other_rect.right()) <= tolerance:
                x = other_rect.right()
                lines.append(QLineF(x, scene_rect.top(), x, scene_rect.bottom()))
            if abs(rect.center().x() - other_rect.center().x()) <= tolerance:
                x = other_rect.center().x()
                lines.append(QLineF(x, scene_rect.top(), x, scene_rect.bottom()))
            if abs(rect.top() - other_rect.top()) <= tolerance:
                y = other_rect.top()
                lines.append(QLineF(scene_rect.left(), y, scene_rect.right(), y))
            if abs(rect.bottom() - other_rect.bottom()) <= tolerance:
                y = other_rect.bottom()
                lines.append(QLineF(scene_rect.left(), y, scene_rect.right(), y))
            if abs(rect.center().y() - other_rect.center().y()) <= tolerance:
                y = other_rect.center().y()
                lines.append(QLineF(scene_rect.left(), y, scene_rect.right(), y))

        self._set_guides(lines)

    def clear_alignment_guides(self) -> None:
        self._set_guides([])

    def _set_guides(self, lines: Iterable[QLineF]) -> None:
        for guide in self._guide_items:
            self.removeItem(guide)
        self._guide_items.clear()
        for line in lines:
            guide = self.addLine(line, self._guide_pen)
            guide.setZValue(10_000)
            self._guide_items.append(guide)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def clear_label_items(self) -> None:
        from .items.base import BaseLabelItem  # local import

        for item in list(self.items()):
            if isinstance(item, BaseLabelItem):
                self.removeItem(item)
        self.clear_alignment_guides()

    def selected_label_items(self) -> list["BaseLabelItem"]:
        from .items.base import BaseLabelItem

        return [item for item in self.selectedItems() if isinstance(item, BaseLabelItem)]

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.save()
        painter.fillRect(rect, self._background_brush)
        label_rect = self.sceneRect()
        painter.fillRect(label_rect, self._label_brush)

        if self._grid_visible:
            grid = self.grid_size_dots()
            if grid > 0:
                left = math.floor(rect.left() / grid) * grid
                top = math.floor(rect.top() / grid) * grid
                right = rect.right()
                bottom = rect.bottom()
                pen_light = QPen(QColor(220, 220, 220, 90))
                pen_light.setWidthF(0.0)
                painter.setPen(pen_light)
                x = left
                while x < right:
                    painter.drawLine(x, rect.top(), x, rect.bottom())
                    x += grid
                y = top
                while y < bottom:
                    painter.drawLine(rect.left(), y, rect.right(), y)
                    y += grid
        painter.restore()

    # ------------------------------------------------------------------
    # Flags
    # ------------------------------------------------------------------
    @property
    def is_restoring(self) -> bool:
        return self._restoring


class RulerWidget(QWidget):
    """Simple ruler widget rendered alongside the graphics view."""

    def __init__(self, orientation: Qt.Orientation, view: "LabelView") -> None:
        super().__init__(view)
        self._orientation = orientation
        self._view = view
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(58, 58, 58))
        pal.setColor(QPalette.WindowText, QColor(230, 230, 230))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setMinimumSize(40, 40)

    def paintEvent(self, event) -> None:  # noqa: D401 - Qt API
        painter = QPainter(self)
        scene = self._view.scene()
        if not isinstance(scene, LabelScene):
            painter.end()
            return

        rect = self.rect()
        painter.fillRect(rect, self.palette().window())
        painter.setPen(self.palette().windowText())

        viewport = self._view.viewport()
        top_left = self._view.mapToScene(QPoint(0, 0))
        bottom_right = self._view.mapToScene(QPoint(viewport.width(), viewport.height()))
        visible = QRectF(top_left, bottom_right).normalized()

        minor_mm = max(scene.dots_to_mm(visible.width()) / 50.0, 1.0)
        major_mm = minor_mm * 5
        minor_mm = max(1.0, round(minor_mm))
        major_mm = max(minor_mm * 5, 5.0)

        if self._orientation == Qt.Horizontal:
            start_mm = math.floor(scene.dots_to_mm(visible.left()) / minor_mm) * minor_mm
            end_mm = scene.dots_to_mm(visible.right())
            base_y = rect.height()
            x = start_mm
            while x <= end_mm + minor_mm:
                px = self._view.mapFromScene(QPointF(scene.mm_to_dots(x), visible.top())).x()
                if math.isclose(x % major_mm, 0.0, abs_tol=1e-6):
                    painter.drawLine(px, base_y, px, base_y - 15)
                    painter.drawText(px + 2, base_y - 17, f"{int(x)}")
                else:
                    painter.drawLine(px, base_y, px, base_y - 8)
                x += minor_mm
        else:
            start_mm = math.floor(scene.dots_to_mm(visible.top()) / minor_mm) * minor_mm
            end_mm = scene.dots_to_mm(visible.bottom())
            base_x = rect.width()
            y = start_mm
            while y <= end_mm + minor_mm:
                py = self._view.mapFromScene(QPointF(visible.left(), scene.mm_to_dots(y))).y()
                if math.isclose(y % major_mm, 0.0, abs_tol=1e-6):
                    painter.drawLine(base_x, py, base_x - 15, py)
                    painter.drawText(2, py - 2, f"{int(y)}")
                else:
                    painter.drawLine(base_x, py, base_x - 8, py)
                y += minor_mm
        painter.end()


class LabelView(QGraphicsView):
    """Graphics view with rulers, zoom and panning capabilities."""

    def __init__(self, scene: LabelScene | None = None, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._zoom = 1.0
        self._ruler_size = 28
        self._panning = False
        self._pan_start = QPoint()
        self._h_ruler = RulerWidget(Qt.Horizontal, self)
        self._v_ruler = RulerWidget(Qt.Vertical, self)
        self._corner = QWidget(self)
        self._corner.setAutoFillBackground(True)
        pal = self._corner.palette()
        pal.setColor(QPalette.Window, QColor(58, 58, 58))
        self._corner.setPalette(pal)
        self.setViewportMargins(self._ruler_size, self._ruler_size, 0, 0)
        self.viewport().installEventFilter(self)
        self._update_rulers_geometry()

    # ------------------------------------------------------------------
    # Zoom helpers
    # ------------------------------------------------------------------
    def zoom_reset(self) -> None:
        self._zoom = 1.0
        self.resetTransform()
        self._update_rulers_geometry()

    def zoom(self, factor: float) -> None:
        self._zoom *= factor
        self.scale(factor, factor)
        self._update_rulers_geometry()

    def set_zoom(self, zoom: float) -> None:
        if zoom <= 0:
            return
        current = self.transform().m11()
        factor = zoom / current
        self._zoom = zoom
        self.scale(factor, factor)
        self._update_rulers_geometry()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: D401 - Qt API
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.25 if delta > 0 else 0.8
            self.zoom(factor)
            event.accept()
            return
        super().wheelEvent(event)
        self._update_rulers_geometry()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            self._update_rulers_geometry()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(QCursor(Qt.ArrowCursor))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: D401 - Qt API
        super().resizeEvent(event)
        self._update_rulers_geometry()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: D401 - Qt API
        super().scrollContentsBy(dx, dy)
        self._update_rulers_geometry()

    def eventFilter(self, obj, event):  # noqa: D401 - Qt API
        if obj is self.viewport() and event.type() == QEvent.Enter:
            self._update_rulers_geometry()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    def _update_rulers_geometry(self) -> None:
        viewport_rect = self.viewport().geometry()
        self._h_ruler.setGeometry(
            self._ruler_size,
            0,
            viewport_rect.width(),
            self._ruler_size,
        )
        self._v_ruler.setGeometry(
            0,
            self._ruler_size,
            self._ruler_size,
            viewport_rect.height(),
        )
        self._corner.setGeometry(0, 0, self._ruler_size, self._ruler_size)
        self._h_ruler.update()
        self._v_ruler.update()

    # ------------------------------------------------------------------
    def setScene(self, scene: QGraphicsScene | None) -> None:  # noqa: N802
        super().setScene(scene)
        self._update_rulers_geometry()
