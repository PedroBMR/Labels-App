"""Layer palette widget for managing scene elements."""

from __future__ import annotations

from functools import partial
from typing import Dict, List

from qt_compat import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    Qt,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)

from .items import GraphicsElementItem, TextGraphicsItem
from .scene import LabelScene


class _LayerListWidget(QListWidget):
    """List widget emitting a signal when rows are reordered."""

    reordered = pyqtSignal()

    def dropEvent(self, event) -> None:  # noqa: D401 - Qt API
        super().dropEvent(event)
        self.reordered.emit()


class _LayerRow(QWidget):
    """Row widget exposing controls for a single layer."""

    activated = pyqtSignal()
    visibilityToggled = pyqtSignal(bool)
    lockToggled = pyqtSignal(bool)
    renameRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self.visibility_button = QToolButton(self)
        self.visibility_button.setCheckable(True)
        self.visibility_button.setAutoRaise(True)
        self.visibility_button.setToolTip("Alternar visibilidade")
        self.visibility_button.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self.visibility_button)

        self.lock_button = QToolButton(self)
        self.lock_button.setCheckable(True)
        self.lock_button.setAutoRaise(True)
        self.lock_button.setToolTip("Travar/Destravar elemento")
        self.lock_button.toggled.connect(self._on_lock_toggled)
        layout.addWidget(self.lock_button)

        self.rename_button = QToolButton(self)
        self.rename_button.setAutoRaise(True)
        self.rename_button.setText("✏️")
        self.rename_button.setToolTip("Renomear elemento")
        self.rename_button.clicked.connect(self.renameRequested.emit)
        layout.addWidget(self.rename_button)

        self.name_button = QToolButton(self)
        self.name_button.setAutoRaise(True)
        self.name_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.name_button.setToolTip("Selecionar elemento")
        self.name_button.clicked.connect(self.activated.emit)
        layout.addWidget(self.name_button, stretch=1)

        self.setFocusPolicy(Qt.NoFocus)
        self.name_button.setFocusPolicy(Qt.NoFocus)
        self.visibility_button.setFocusPolicy(Qt.NoFocus)
        self.lock_button.setFocusPolicy(Qt.NoFocus)
        self.rename_button.setFocusPolicy(Qt.NoFocus)

    def set_visibility(self, visible: bool) -> None:
        self._updating = True
        self.visibility_button.setChecked(visible)
        self.visibility_button.setText("👁️" if visible else "🚫")
        self._updating = False

    def set_locked(self, locked: bool) -> None:
        self._updating = True
        self.lock_button.setChecked(locked)
        self.lock_button.setText("🔒" if locked else "🔓")
        self._updating = False

    def set_name(self, name: str) -> None:
        self.name_button.setText(name)

    def set_selected(self, selected: bool) -> None:
        weight = "bold" if selected else "normal"
        self.name_button.setStyleSheet(f"font-weight: {weight};")

    def _on_visibility_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        self.visibility_button.setText("👁️" if checked else "🚫")
        self.visibilityToggled.emit(checked)

    def _on_lock_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        self.lock_button.setText("🔒" if checked else "🔓")
        self.lockToggled.emit(checked)

    def mousePressEvent(self, event) -> None:  # noqa: D401 - Qt API
        if event.button() == Qt.LeftButton:
            self.activated.emit()
        super().mousePressEvent(event)


class LayerPanel(QWidget):
    """Palette listing scene elements ordered by their stacking layer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene: LabelScene | None = None
        self._updating_selection = False
        self._row_items: Dict[GraphicsElementItem | TextGraphicsItem, QListWidgetItem] = {}
        self._widgets: Dict[GraphicsElementItem | TextGraphicsItem, _LayerRow] = {}
        self._change_handlers: Dict[
            GraphicsElementItem | TextGraphicsItem, object
        ] = {}

        self.setMinimumWidth(220)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.list_widget = _LayerListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self.list_widget.reordered.connect(self._apply_reorder)
        layout.addWidget(self.list_widget, stretch=1)

    # ------------------------------------------------------------------
    def set_scene(self, scene: LabelScene | None) -> None:
        if self._scene is not None:
            try:
                self._scene.selectionChanged.disconnect(self._sync_selection)
            except Exception:  # pragma: no cover - defensive
                pass
            try:
                self._scene.itemsChanged.disconnect(self.refresh)
            except Exception:  # pragma: no cover - defensive
                pass
        self._scene = scene
        if scene is not None:
            scene.selectionChanged.connect(self._sync_selection)
            scene.itemsChanged.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._disconnect_item_handlers()
        self._row_items.clear()
        self._widgets.clear()
        self.list_widget.clear()

        if self._scene is None:
            return

        items: List[GraphicsElementItem | TextGraphicsItem] = []
        for item in self._scene.items(Qt.DescendingOrder):
            if isinstance(item, (GraphicsElementItem, TextGraphicsItem)):
                items.append(item)

        for item in items:
            row_widget = _LayerRow(self.list_widget)
            row_widget.set_visibility(item.isVisible())
            row_widget.set_locked(getattr(item, "_locked", False))
            row_widget.set_name(self._display_name(item))
            row_widget.visibilityToggled.connect(
                partial(self._toggle_visibility, item)
            )
            row_widget.lockToggled.connect(partial(self._toggle_lock, item))
            row_widget.renameRequested.connect(partial(self._rename_item, item))
            row_widget.activated.connect(partial(self._select_item, item))

            list_item = QListWidgetItem(self.list_widget)
            list_item.setSizeHint(row_widget.sizeHint())
            list_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, row_widget)

            handler = partial(self._on_item_changed, item)
            item.changed.connect(handler)
            self._change_handlers[item] = handler
            self._row_items[item] = list_item
            self._widgets[item] = row_widget

        self._sync_selection()

    def _disconnect_item_handlers(self) -> None:
        for item, handler in list(self._change_handlers.items()):
            try:
                item.changed.disconnect(handler)
            except Exception:  # pragma: no cover - defensive
                pass
        self._change_handlers.clear()

    # ------------------------------------------------------------------
    def _display_name(self, item: GraphicsElementItem | TextGraphicsItem) -> str:
        name = str(item.element.get("name", "")).strip()
        if name:
            return name
        element_type = str(item.element.get("type", "")).lower()
        return self._scene.default_name(element_type) if self._scene else "Elemento"

    def _on_item_changed(self, item: GraphicsElementItem | TextGraphicsItem) -> None:
        widget = self._widgets.get(item)
        if not widget:
            return
        widget.set_visibility(item.isVisible())
        widget.set_locked(getattr(item, "_locked", False))
        widget.set_name(self._display_name(item))
        selected_items = set(self._scene.selected_items()) if self._scene else set()
        widget.set_selected(item in selected_items)

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if self._updating_selection or self._scene is None:
            return
        if current is None:
            self._scene.clearSelection()
            return
        item = current.data(Qt.UserRole)
        if isinstance(item, (GraphicsElementItem, TextGraphicsItem)):
            self._select_item(item)

    def _select_item(
        self, item: GraphicsElementItem | TextGraphicsItem
    ) -> None:
        if self._scene is None:
            return
        self._updating_selection = True
        self._scene.clearSelection()
        item.setSelected(True)
        self._scene.update()
        list_item = self._row_items.get(item)
        if list_item is not None:
            index = self.list_widget.row(list_item)
            self.list_widget.setCurrentRow(index)
        self._updating_selection = False
        self._highlight_selection()

    def _sync_selection(self) -> None:
        if self._scene is None or self._updating_selection:
            return
        selected = self._scene.selected_items()
        self._updating_selection = True
        if selected:
            list_item = self._row_items.get(selected[0])
            if list_item is not None:
                index = self.list_widget.row(list_item)
                self.list_widget.setCurrentRow(index)
        else:
            self.list_widget.setCurrentRow(-1)
        self._updating_selection = False
        self._highlight_selection()

    def _highlight_selection(self) -> None:
        if self._scene is None:
            return
        selected = set(self._scene.selected_items())
        for item, widget in self._widgets.items():
            widget.set_selected(item in selected)

    # ------------------------------------------------------------------
    def _toggle_visibility(
        self, item: GraphicsElementItem | TextGraphicsItem, visible: bool
    ) -> None:
        if self._scene is None:
            return
        self._scene.change_property(item, "hidden", not visible)
        self._on_item_changed(item)

    def _toggle_lock(
        self, item: GraphicsElementItem | TextGraphicsItem, locked: bool
    ) -> None:
        item.lock(locked)
        self._on_item_changed(item)

    def _rename_item(self, item: GraphicsElementItem | TextGraphicsItem) -> None:
        if self._scene is None:
            return
        current_name = str(item.element.get("name", ""))
        element_type = str(item.element.get("type", "")).lower()
        new_name, accepted = QInputDialog.getText(
            self,
            "Renomear elemento",
            "Nome da camada:",
            text=current_name or self._scene.default_name(element_type),
        )
        if not accepted:
            return
        unique = self._scene.unique_name(
            new_name,
            element_type=element_type,
            exclude=item,
        )
        if unique != current_name:
            self._scene.change_property(item, "name", unique)
        self._on_item_changed(item)

    def _apply_reorder(self) -> None:
        if self._scene is None:
            return
        order: List[GraphicsElementItem | TextGraphicsItem] = []
        for index in range(self.list_widget.count()):
            row_item = self.list_widget.item(index)
            item = row_item.data(Qt.UserRole)
            if isinstance(item, (GraphicsElementItem, TextGraphicsItem)):
                order.append(item)
        if order:
            self._scene.reorder_items(order)

