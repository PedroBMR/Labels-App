"""Graphics view used by the label editor."""

from __future__ import annotations

from qt_compat import QGraphicsView, QMouseEvent, QPainter, QPointF, Qt, pyqtSignal


class LabelView(QGraphicsView):
    """Customised view providing zoom and panning helpers."""

    viewportChanged = pyqtSignal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._panning = False
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
            factor = 1.2 if angle > 0 else 1 / 1.2
            self.scale(factor, factor)
            event.accept()
            self.viewportChanged.emit()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.MiddleButton or (
            event.button() == Qt.LeftButton and event.modifiers() & Qt.SpaceModifier
        ):
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D401 - Qt API
        if self._panning and self._last_pan_pos is not None:
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
        if self._panning and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            self.viewportChanged.emit()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: D401 - Qt API
        super().resizeEvent(event)
        self.viewportChanged.emit()
