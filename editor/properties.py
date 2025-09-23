"""Dockable property inspector for label items."""
from __future__ import annotations

from functools import partial
from typing import Any

from qt_compat import (
    QColor,
    QColorDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDockWidget,
    QPlainTextEdit,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QPushButton,
    QWidget,
    Qt,
)

from .items import BaseLabelItem, PropertyField
from .scene import LabelScene


class PropertyInspector(QDockWidget):
    """Widget that edits properties from the currently selected graphics item."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Propriedades", parent)
        self.setObjectName("propertyInspector")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        container = QWidget(self)
        self._layout = QFormLayout(container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)
        self._placeholder: QLabel | None = None
        self._show_placeholder()
        self.setWidget(container)
        self._scene: LabelScene | None = None
        self._current_item: BaseLabelItem | None = None
        self._field_widgets: dict[str, QWidget] = {}
        self._geometry_widgets: dict[str, QDoubleSpinBox] = {}
        self._updating = False

    # ------------------------------------------------------------------
    def bind_scene(self, scene: LabelScene) -> None:
        if self._scene is scene:
            return
        if self._scene is not None:
            try:
                self._scene.selectionChanged.disconnect(self._on_selection_changed)
            except Exception:
                pass
        self._scene = scene
        scene.selectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        if self._scene is None:
            return
        items = self._scene.selected_label_items()
        if len(items) == 1:
            self._set_item(items[0])
        else:
            self._set_item(None)

    def _set_item(self, item: BaseLabelItem | None) -> None:
        if self._current_item is item:
            return
        if self._current_item is not None:
            try:
                self._current_item.propertiesChanged.disconnect(self._refresh_current_item)
            except Exception:
                pass
        self._current_item = item
        self._rebuild()
        if self._current_item is not None:
            self._current_item.propertiesChanged.connect(self._refresh_current_item)

    # ------------------------------------------------------------------
    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout():
                item.layout().deleteLater()

    def _show_placeholder(self) -> None:
        placeholder = QLabel("Selecione um item para editar.")
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._layout.addRow(placeholder)
        self._placeholder = placeholder

    def _rebuild(self) -> None:
        self._clear_layout()
        self._field_widgets.clear()
        self._geometry_widgets.clear()
        if self._current_item is None or self._scene is None:
            self._show_placeholder()
            return
        self._add_geometry_controls()
        values = self._current_item.property_values()
        for field in self._current_item.property_fields():
            widget = self._create_editor(field, values.get(field.name))
            self._layout.addRow(f"{field.label}:", widget)
            self._field_widgets[field.name] = widget

    # ------------------------------------------------------------------
    def _add_geometry_controls(self) -> None:
        if self._current_item is None or self._scene is None:
            return
        item = self._current_item
        scene = self._scene
        rect = item.rect()
        pos = item.pos()
        geometry = {
            "x": scene.dots_to_mm(pos.x()),
            "y": scene.dots_to_mm(pos.y()),
            "width": scene.dots_to_mm(rect.width()),
            "height": scene.dots_to_mm(rect.height()),
            "rotation": item.rotation(),
        }
        ranges = {
            "x": (-1000.0, 5000.0),
            "y": (-1000.0, 5000.0),
            "width": (1.0, 5000.0),
            "height": (1.0, 5000.0),
            "rotation": (-360.0, 360.0),
        }
        for name, value in geometry.items():
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(*ranges[name])
            spin.setValue(value)
            spin.setSingleStep(0.5 if name in {"x", "y"} else 1.0)
            spin.valueChanged.connect(partial(self._on_geometry_changed, name))
            label = "Rotação (°)" if name == "rotation" else f"{name.title()} (mm)"
            self._layout.addRow(label, spin)
            self._geometry_widgets[name] = spin

    # ------------------------------------------------------------------
    def _create_editor(self, field: PropertyField, value: Any | None) -> QWidget:
        if field.field_type in {"text", "multiline"}:
            if field.multiline:
                editor = QPlainTextEdit()
                editor.setPlainText(str(value or ""))
                editor.textChanged.connect(lambda f=field.name, w=editor: self._apply_property(f, w.toPlainText()))
                return editor
            line = QLineEdit(str(value or ""))
            line.textChanged.connect(lambda text, f=field.name: self._apply_property(f, text))
            return line
        if field.field_type == "choice":
            combo = QComboBox()
            for option in field.options or []:
                combo.addItem(str(option))
            if value is not None:
                index = combo.findText(str(value))
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.currentTextChanged.connect(lambda text, f=field.name: self._apply_property(f, text))
            return combo
        if field.field_type == "bool":
            check = QCheckBox()
            check.setChecked(bool(value))
            check.toggled.connect(lambda state, f=field.name: self._apply_property(f, state))
            return check
        if field.field_type == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(field.minimum or -1e6, field.maximum or 1e6)
            spin.setSingleStep(field.step or 0.1)
            spin.setValue(float(value or 0.0))
            spin.valueChanged.connect(lambda val, f=field.name: self._apply_property(f, val))
            return spin
        if field.field_type == "int":
            spin = QSpinBox()
            spin.setRange(int(field.minimum or -10_000), int(field.maximum or 10_000))
            spin.setSingleStep(int(field.step or 1))
            spin.setValue(int(value or 0))
            spin.valueChanged.connect(lambda val, f=field.name: self._apply_property(f, val))
            return spin
        if field.field_type == "font":
            font_box = QFontComboBox()
            if isinstance(value, str):
                font_box.setCurrentFont(font_box.font())
                font_box.setCurrentText(value)
            font_box.currentTextChanged.connect(lambda text, f=field.name: self._apply_property(f, text))
            return font_box
        if field.field_type == "color":
            button = QPushButton()
            color = QColor(value) if value is not None else QColor("#000000")
            button.setProperty("current-color", color)
            button.setStyleSheet(f"background:{color.name()};")
            button.clicked.connect(lambda *, f=field.name, b=button: self._choose_color(f, b))
            return button
        if field.field_type == "path":
            return self._create_path_editor(field.name, str(value or ""))
        line = QLineEdit(str(value or ""))
        line.textChanged.connect(lambda text, f=field.name: self._apply_property(f, text))
        return line

    def _create_path_editor(self, field: str, value: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        line = QLineEdit(value)
        browse = QPushButton("…")
        layout.addWidget(line)
        layout.addWidget(browse)
        line.textChanged.connect(lambda text, f=field: self._apply_property(f, text))
        browse.clicked.connect(lambda: self._browse_file(field, line))
        return container

    # ------------------------------------------------------------------
    def _browse_file(self, field: str, line_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo")
        if path:
            line_edit.setText(path)
            self._apply_property(field, path)

    def _choose_color(self, field: str, button: QPushButton) -> None:
        current = button.property("current-color")
        if isinstance(current, QColor):
            initial = current
        else:
            initial = QColor("#000000")
        color = QColorDialog.getColor(initial, self, "Selecionar cor")
        if color.isValid():
            button.setProperty("current-color", color)
            button.setStyleSheet(f"background:{color.name()};")
            self._apply_property(field, color)

    # ------------------------------------------------------------------
    def _apply_property(self, name: str, value: Any) -> None:
        if self._updating or self._current_item is None:
            return
        scene = self._scene
        if scene is None:
            return
        item = self._current_item
        before = scene.capture_item_state(item)
        item.blockSignals(True)
        try:
            item.set_property(name, value)
        finally:
            item.blockSignals(False)
        after = scene.capture_item_state(item)
        scene.push_state(item, before, after, f"Editar {name}")
        self._refresh_current_item()

    def _on_geometry_changed(self, name: str, value: float) -> None:
        if self._updating or self._current_item is None or self._scene is None:
            return
        item = self._current_item
        scene = self._scene
        before = scene.capture_item_state(item)
        item.blockSignals(True)
        try:
            if name == "x":
                item.setPos(scene.mm_to_dots(value), item.pos().y())
            elif name == "y":
                item.setPos(item.pos().x(), scene.mm_to_dots(value))
            elif name == "width":
                item.set_size(scene.mm_to_dots(value), item.rect().height())
            elif name == "height":
                item.set_size(item.rect().width(), scene.mm_to_dots(value))
            elif name == "rotation":
                item.set_rotation(value)
        finally:
            item.blockSignals(False)
        after = scene.capture_item_state(item)
        scene.push_state(item, before, after, "Editar geometria")
        self._refresh_current_item()

    # ------------------------------------------------------------------
    def _refresh_current_item(self) -> None:
        if self._current_item is None or self._scene is None:
            return
        self._updating = True
        try:
            item = self._current_item
            rect = item.rect()
            pos = item.pos()
            if "x" in self._geometry_widgets:
                self._geometry_widgets["x"].setValue(self._scene.dots_to_mm(pos.x()))
            if "y" in self._geometry_widgets:
                self._geometry_widgets["y"].setValue(self._scene.dots_to_mm(pos.y()))
            if "width" in self._geometry_widgets:
                self._geometry_widgets["width"].setValue(self._scene.dots_to_mm(rect.width()))
            if "height" in self._geometry_widgets:
                self._geometry_widgets["height"].setValue(self._scene.dots_to_mm(rect.height()))
            if "rotation" in self._geometry_widgets:
                self._geometry_widgets["rotation"].setValue(item.rotation())
            values = item.property_values()
            for name, widget in self._field_widgets.items():
                self._update_widget_value(widget, values.get(name))
        finally:
            self._updating = False

    def _update_widget_value(self, widget: QWidget, value: Any) -> None:
        if isinstance(widget, QLineEdit):
            widget.setText(str(value or ""))
        elif isinstance(widget, QPlainTextEdit):
            widget.setPlainText(str(value or ""))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value or 0.0))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value or 0))
        elif isinstance(widget, QFontComboBox):
            if isinstance(value, str):
                widget.setCurrentText(value)
        elif isinstance(widget, QPushButton) and widget.property("current-color") is not None:
            color = QColor(value) if value is not None else QColor("#000000")
            widget.setProperty("current-color", color)
            widget.setStyleSheet(f"background:{color.name()};")

*** End Patch
