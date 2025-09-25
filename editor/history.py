"""Undo history panel with thumbnail navigation."""

from __future__ import annotations

from typing import Optional

from qt_compat import (
    QListWidget,
    QListWidgetItem,
    QSize,
    QVBoxLayout,
    QWidget,
    QIcon,
    Qt,
)

from .scene import LabelScene


class UndoHistoryPanel(QWidget):
    """Display undo/redo history entries with canvas thumbnails."""

    def __init__(self, scene: Optional[LabelScene] = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene: LabelScene | None = None
        self._updating_selection = False
        self._icon_size = QSize(112, 112)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.list_widget = QListWidget(self)
        self.list_widget.setIconSize(self._icon_size)
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.list_widget.itemActivated.connect(self._on_item_activated)

        layout.addWidget(self.list_widget)

        if scene is not None:
            self.set_scene(scene)

    # ------------------------------------------------------------------
    def set_scene(self, scene: LabelScene | None) -> None:
        if self._scene is scene:
            return
        if self._scene is not None:
            self._scene.historyChanged.disconnect(self._refresh_items)
            self._scene.undo_stack.indexChanged.disconnect(self._on_index_changed)
        self._scene = scene
        if self._scene is not None:
            self._scene.historyChanged.connect(self._refresh_items)
            self._scene.undo_stack.indexChanged.connect(self._on_index_changed)
            self._refresh_items()
            self._on_index_changed(self._scene.undo_stack.index())
        else:
            self.list_widget.clear()

    # ------------------------------------------------------------------
    def reset_history(self) -> None:
        if self._scene is None:
            self.list_widget.clear()
            return
        self._scene.reset_history_snapshots()
        self._refresh_items()
        self._on_index_changed(self._scene.undo_stack.index())

    # ------------------------------------------------------------------
    def _refresh_items(self) -> None:
        scene = self._scene
        if scene is None:
            self.list_widget.clear()
            return
        stack = scene.undo_stack
        count = stack.count()
        snapshots = scene.history_snapshots()
        if len(snapshots) < count + 1:
            snapshots.extend(scene.capture_thumbnail() for _ in range(count + 1 - len(snapshots)))

        self._updating_selection = True
        try:
            self.list_widget.clear()
            for index in range(count + 1):
                if index == 0:
                    text = "Estado inicial"
                else:
                    command = stack.command(index - 1)
                    text = command.text() or f"Ação {index}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, index)
                if index < len(snapshots):
                    pixmap = snapshots[index]
                    if not pixmap.isNull():
                        icon = QIcon(
                            pixmap.scaled(
                                self._icon_size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                        )
                        item.setIcon(icon)
                self.list_widget.addItem(item)
        finally:
            self._updating_selection = False
        self._select_row(scene.undo_stack.index())

    def _select_row(self, index: int) -> None:
        if index < 0 or index >= self.list_widget.count():
            self.list_widget.clearSelection()
            return
        self._updating_selection = True
        try:
            self.list_widget.setCurrentRow(index)
        finally:
            self._updating_selection = False

    def _on_index_changed(self, index: int) -> None:
        scene = self._scene
        if scene is None:
            return
        expected_count = scene.undo_stack.count() + 1
        if self.list_widget.count() != expected_count:
            self._refresh_items()
            return
        self._select_row(index)

    def _on_row_changed(self, row: int) -> None:
        if self._updating_selection:
            return
        scene = self._scene
        if scene is None or row < 0:
            return
        scene.undo_stack.setIndex(row)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        row = item.data(Qt.UserRole)
        if isinstance(row, int):
            self._on_row_changed(row)
