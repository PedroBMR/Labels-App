"""Graphics view used by the label editor."""

from __future__ import annotations

from qt_compat import QGraphicsView, QMouseEvent, QPainter, QPointF, Qt, pyqtSignal


class LabelView(QGraphicsView):
    """Customised view providing zoom and panning helpers."""

    viewportChanged = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._space_panning = False
        self._middle_panning = False
        self._last_pan_pos: QPointF | None = None
        self.horizontalScrollBar().valueChanged.connect(
            self._notify_viewport_change
        )
        self.verticalScrollBar().valueChanged.connect(self._notify_viewport_change)

    def _notify_viewport_change(self, _value: int) -> None:
        self.viewportChanged.emit()

    # ------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: D401 - Qt API
        if event.modifiers() & Qt.ControlModifier:
            angle = event.angleDelta().y()
            if angle:
                factor = 1.0015 ** angle
                self.scale(factor, factor)
                event.accept()
                self.viewportChanged.emit()
                return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: D401 - Qt API
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: D401 - Qt API
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = False
            if not self._middle_panning:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                self.viewport().unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.MiddleButton:
            self._middle_panning = True
            self._last_pan_pos = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if self._middle_panning and self._last_pan_pos is not None:
            delta = event.pos() - self._last_pan_pos
            self._last_pan_pos = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            self.viewportChanged.emit()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.MiddleButton and self._middle_panning:
            self._middle_panning = False
            self._last_pan_pos = None
            if self._space_panning:
                self.viewport().setCursor(Qt.OpenHandCursor)
            else:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                self.viewport().unsetCursor()
            event.accept()
            self.viewportChanged.emit()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: D401 - Qt API
        super().resizeEvent(event)
        self.viewportChanged.emit()
