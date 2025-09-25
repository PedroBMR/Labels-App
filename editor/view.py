"""Graphics view used by the label editor."""

from __future__ import annotations

from qt_compat import (
    QAction,
    QGraphicsView,
    QMenu,
    QMouseEvent,
    QPainter,
    QPointF,
    Qt,
    pyqtSignal,
)

from .items import EditableTextItem


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
        if event.key() in {Qt.Key_Delete, Qt.Key_Backspace}:
            if self._handle_delete_request():
                event.accept()
                return
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

    def contextMenuEvent(self, event) -> None:  # noqa: D401 - Qt API
        scene = self.scene()
        if scene is None:
            return

        menu = QMenu(self)

        delete_action = QAction("Delete", menu)
        delete_action.triggered.connect(self._handle_delete_request)
        delete_action.setEnabled(self._can_delete_selection())
        menu.addAction(delete_action)

        duplicate_action = QAction("Duplicate", menu)
        duplicate_action.triggered.connect(self._handle_duplicate_request)
        duplicate_action.setEnabled(scene.can_duplicate_selected_items())
        menu.addAction(duplicate_action)

        selected = scene.selected_items()
        any_locked = any(getattr(item, "_locked", False) for item in selected)
        lock_label = "Unlock" if any_locked else "Lock"
        lock_state = False if any_locked else True
        lock_action = QAction(lock_label, menu)
        lock_action.setEnabled(bool(selected))
        lock_action.triggered.connect(
            lambda checked=False, state=lock_state: self._handle_lock_request(state)
        )
        menu.addAction(lock_action)

        menu.exec(event.globalPos())

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

    # ------------------------------------------------------------------
    def _focused_text_item(self) -> EditableTextItem | None:
        scene = self.scene()
        if not scene:
            return None
        focus_item = scene.focusItem()
        if isinstance(focus_item, EditableTextItem):
            return focus_item
        return None

    def _handle_delete_request(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        focused = self._focused_text_item()
        if focused and focused.is_editing():
            return False
        removed = scene.remove_selected_items()
        if removed:
            self.viewportChanged.emit()
        return removed

    def _handle_duplicate_request(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        duplicated = scene.duplicate_selected_items()
        if duplicated:
            self.viewportChanged.emit()
        return duplicated

    def _handle_lock_request(self, locked: bool) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        changed = scene.set_selected_items_locked(locked)
        if changed:
            self.viewportChanged.emit()
        return changed

    def _can_delete_selection(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        return scene.can_remove_selected_items()
