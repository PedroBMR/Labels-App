"""Property inspector for the label editor."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping

from qt_compat import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .items import GraphicsElementItem, TextGraphicsItem
from .scene import LabelScene


class PropertyPanel(QWidget):
    """Widget exposing editable properties for the selected element."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PropertyPanel")
        self._scene: LabelScene | None = None
        self._item: GraphicsElementItem | TextGraphicsItem | None = None
        self._current_element_type: str | None = None
        self._connected_item: GraphicsElementItem | TextGraphicsItem | None = None

        self._required_rules: list[dict[str, Any]] = []
        self._tab_sections: dict[str, QWidget] = {}
        self._tab_order = ["position", "text", "barcode", "qr", "image", "shape"]
        self._element_tab_map = {
            "text": {"text"},
            "barcode": {"barcode"},
            "qr": {"qr"},
            "qrcode": {"qr"},
            "image": {"image"},
            "shape": {"shape"},
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs)

        # --- Position ---------------------------------------------------
        self.position_tab = QWidget()
        self.general_form = QFormLayout(self.position_tab)
        self.general_form.setContentsMargins(4, 4, 4, 4)
        self.general_form.setSpacing(4)
        self.general_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nome exibido na paleta de camadas")
        self.name_edit.editingFinished.connect(self._commit_name_edit)
        self.general_form.addRow("Nome", self.name_edit)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-1000, 1000)
        self.x_spin.setSuffix(" mm")
        self.x_spin.valueChanged.connect(partial(self._apply_numeric, "x_mm"))
        self.general_form.addRow("X", self.x_spin)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-1000, 1000)
        self.y_spin.setSuffix(" mm")
        self.y_spin.valueChanged.connect(partial(self._apply_numeric, "y_mm"))
        self.general_form.addRow("Y", self.y_spin)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 1000)
        self.width_spin.setSuffix(" mm")
        self.width_spin.valueChanged.connect(partial(self._apply_numeric, "width_mm"))
        self.general_form.addRow("Largura", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1, 1000)
        self.height_spin.setSuffix(" mm")
        self.height_spin.valueChanged.connect(partial(self._apply_numeric, "height_mm"))
        self.general_form.addRow("Altura", self.height_spin)

        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360, 360)
        self.rotation_spin.setSuffix(" º")
        self.rotation_spin.valueChanged.connect(
            partial(self._apply_numeric, "rotation")
        )
        self.general_form.addRow("Rotação", self.rotation_spin)

        self.lock_check = QCheckBox("Travar movimento")
        self.lock_check.toggled.connect(self._toggle_lock)
        self.general_form.addRow(self.lock_check)

        self.hidden_check = QCheckBox("Ocultar elemento")
        self.hidden_check.toggled.connect(self._toggle_hidden)
        self.general_form.addRow(self.hidden_check)

        self._tab_sections["position"] = self.position_tab
        self.tabs.addTab(self.position_tab, "Posição")

        # --- Text -------------------------------------------------------
        self.text_tab = QWidget()
        self.text_form = QFormLayout(self.text_tab)
        self.text_form.setContentsMargins(4, 4, 4, 4)
        self.text_form.setSpacing(4)
        self.text_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.text_content = QTextEdit()
        self.text_content.setPlaceholderText("Conteúdo com variáveis {exemplo}")
        self.text_content.setMinimumHeight(72)
        self.text_content.textChanged.connect(self._on_text_changed)
        self.text_form.addRow(
            self._make_label("Conteúdo", required=True),
            self.text_content,
        )

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 200)
        self.font_size_spin.valueChanged.connect(
            partial(self._apply_font_property, "size")
        )
        self.text_form.addRow("Tamanho", self.font_size_spin)

        self.bold_check = QCheckBox("Negrito")
        self.bold_check.toggled.connect(partial(self._apply_font_property, "bold"))
        self.text_form.addRow(self.bold_check)

        self.italic_check = QCheckBox("Itálico")
        self.italic_check.toggled.connect(partial(self._apply_font_property, "italic"))
        self.text_form.addRow(self.italic_check)

        self.align_combo = QComboBox()
        self.align_combo.addItems(["left", "center", "right"])
        self.align_combo.currentTextChanged.connect(
            partial(self._apply_property, "align")
        )
        self.text_form.addRow("Alinhamento", self.align_combo)

        self.font_path_line = QLineEdit()
        self.font_path_line.setPlaceholderText("Fonte TTF (opcional)")
        self.font_path_line.textChanged.connect(self._update_font_path)
        font_button = QPushButton("Escolher…")
        font_button.clicked.connect(self._choose_font)
        font_container = QWidget()
        font_layout = QHBoxLayout(font_container)
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.setSpacing(4)
        font_layout.addWidget(self.font_path_line)
        font_layout.addWidget(font_button)
        self.text_form.addRow("Arquivo da fonte", font_container)

        self._register_required_field(
            widget=self.text_content,
            validator=lambda: bool(self.text_content.toPlainText().strip()),
            message="Informe o conteúdo que será impresso no elemento de texto.",
            category="text",
            layout=self.text_form,
        )

        self._tab_sections["text"] = self.text_tab
        self.tabs.addTab(self.text_tab, "Texto")

        # --- Barcode ----------------------------------------------------
        self.barcode_tab = QWidget()
        self.barcode_form = QFormLayout(self.barcode_tab)
        self.barcode_form.setContentsMargins(4, 4, 4, 4)
        self.barcode_form.setSpacing(4)

        self.barcode_value = QLineEdit()
        self.barcode_value.setPlaceholderText("Dados do código")
        self.barcode_value.textChanged.connect(self._on_barcode_value_changed)
        self.barcode_form.addRow(
            self._make_label("Dados", required=True),
            self.barcode_value,
        )

        self.barcode_type = QComboBox()
        self.barcode_type.addItems(["code128", "ean13", "code39", "code93"])
        self.barcode_type.currentTextChanged.connect(
            partial(self._apply_property, "symbology")
        )
        self.barcode_form.addRow("Simbolia", self.barcode_type)

        self.barcode_module = QDoubleSpinBox()
        self.barcode_module.setRange(0.1, 10.0)
        self.barcode_module.setSingleStep(0.1)
        self.barcode_module.setValue(0.5)
        self.barcode_module.setSuffix(" mm")
        self.barcode_module.valueChanged.connect(
            partial(self._apply_property, "module_mm")
        )
        self.barcode_form.addRow("Espessura", self.barcode_module)

        self.barcode_human = QCheckBox("Exibir texto")
        self.barcode_human.toggled.connect(partial(self._apply_property, "human"))
        self.barcode_form.addRow(self.barcode_human)

        self._register_required_field(
            widget=self.barcode_value,
            validator=lambda: bool(self.barcode_value.text().strip()),
            message="Preencha os dados que compõem o código de barras.",
            category="barcode",
            layout=self.barcode_form,
        )

        self._tab_sections["barcode"] = self.barcode_tab
        self.tabs.addTab(self.barcode_tab, "Código de barras")

        # --- QR ---------------------------------------------------------
        self.qr_tab = QWidget()
        self.qr_form = QFormLayout(self.qr_tab)
        self.qr_form.setContentsMargins(4, 4, 4, 4)
        self.qr_form.setSpacing(4)

        self.qr_value = QLineEdit()
        self.qr_value.textChanged.connect(self._on_qr_value_changed)
        self.qr_form.addRow(
            self._make_label("Dados", required=True),
            self.qr_value,
        )

        self.qr_error = QComboBox()
        self.qr_error.addItems(["L", "M", "Q", "H"])
        self.qr_error.currentTextChanged.connect(
            partial(self._apply_property, "error")
        )
        self.qr_form.addRow("Correção", self.qr_error)

        self._register_required_field(
            widget=self.qr_value,
            validator=lambda: bool(self.qr_value.text().strip()),
            message="Informe o conteúdo que será codificado no QR Code.",
            category="qr",
            layout=self.qr_form,
        )

        self._tab_sections["qr"] = self.qr_tab
        self.tabs.addTab(self.qr_tab, "QR Code")

        # --- Image ------------------------------------------------------
        self.image_tab = QWidget()
        self.image_form = QFormLayout(self.image_tab)
        self.image_form.setContentsMargins(4, 4, 4, 4)
        self.image_form.setSpacing(4)

        self.image_path = QLineEdit()
        self.image_path.textChanged.connect(self._update_image_source)
        self.image_button = QPushButton("Escolher…")
        self.image_button.clicked.connect(self._choose_image)
        image_container = QWidget()
        image_layout = QHBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(4)
        image_layout.addWidget(self.image_path)
        image_layout.addWidget(self.image_button)
        self.image_form.addRow(
            self._make_label("Arquivo", required=True),
            image_container,
        )

        self.image_fit = QComboBox()
        self.image_fit.addItems(["contain", "cover"])
        self.image_fit.currentTextChanged.connect(partial(self._apply_property, "fit"))
        self.image_form.addRow("Ajuste", self.image_fit)

        self._register_required_field(
            widget=self.image_path,
            validator=lambda: bool(self.image_path.text().strip()),
            message="Selecione o arquivo que será impresso na imagem.",
            category="image",
            layout=self.image_form,
        )

        self._tab_sections["image"] = self.image_tab
        self.tabs.addTab(self.image_tab, "Imagem")

        # --- Shape ------------------------------------------------------
        self.shape_tab = QWidget()
        self.shape_form = QFormLayout(self.shape_tab)
        self.shape_form.setContentsMargins(4, 4, 4, 4)
        self.shape_form.setSpacing(4)

        self.shape_kind = QComboBox()
        self.shape_kind.addItems(["rect", "line"])
        self.shape_kind.currentTextChanged.connect(
            partial(self._apply_property, "kind")
        )
        self.shape_form.addRow("Tipo", self.shape_kind)

        self.shape_thickness = QDoubleSpinBox()
        self.shape_thickness.setRange(0.1, 10.0)
        self.shape_thickness.setSingleStep(0.1)
        self.shape_thickness.setSuffix(" mm")
        self.shape_thickness.valueChanged.connect(
            partial(self._apply_property, "thickness_mm")
        )
        self.shape_form.addRow("Espessura", self.shape_thickness)

        self._tab_sections["shape"] = self.shape_tab
        self.tabs.addTab(self.shape_tab, "Formas")

        self.setStyleSheet(
            """
#PropertyPanel QLineEdit[invalid="true"],
#PropertyPanel QTextEdit[invalid="true"],
#PropertyPanel QWidget > QTextEdit[invalid="true"] {
    border: 1px solid #b3261e;
    border-radius: 4px;
}
#PropertyPanel QLabel#validationHintText {
    color: #b3261e;
    font-size: 11px;
}
#PropertyPanel QWidget#requiredLabel QLabel {
    font-weight: 600;
}
"""
        )

        self.setDisabled(True)

    # ------------------------------------------------------------------
    def _make_label(self, text: str, *, required: bool = False) -> QWidget:
        if not required:
            label = QLabel(text)
            label.setObjectName("formLabel")
            return label

        container = QWidget()
        container.setObjectName("requiredLabel")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.SP_ArrowRight)
        icon_label.setPixmap(icon.pixmap(12, 12))
        layout.addWidget(icon_label)
        text_label = QLabel(text)
        text_label.setObjectName("formLabel")
        layout.addWidget(text_label)
        layout.addStretch(1)
        return container

    def _create_validation_hint(self, message: str) -> QWidget:
        hint = QWidget()
        layout = QHBoxLayout(hint)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(14, 14))
        layout.addWidget(icon_label)
        text_label = QLabel(message)
        text_label.setObjectName("validationHintText")
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)
        hint.setProperty("message", message)
        hint.hide()
        return hint

    def _register_required_field(
        self,
        *,
        widget: QWidget,
        validator: Callable[[], bool],
        message: str,
        category: str,
        layout: QFormLayout,
    ) -> None:
        hint = self._create_validation_hint(message)
        layout.addRow("", hint)
        self._required_rules.append(
            {
                "widget": widget,
                "validator": validator,
                "hint": hint,
                "category": category,
            }
        )
        self._apply_validation_feedback(widget, hint, True)

    def _apply_validation_feedback(
        self, widget: QWidget, hint: QWidget, is_valid: bool
    ) -> None:
        targets = [widget]
        if isinstance(widget, QTextEdit):
            targets.append(widget.viewport())
        for target in targets:
            target.setProperty("invalid", not is_valid)
            style = target.style()
            if style is not None:
                style.unpolish(target)
                style.polish(target)
            target.update()
        widget.setAccessibleDescription(
            hint.property("message") if not is_valid else ""
        )
        hint.setVisible(not is_valid)

    def _active_required_categories(self) -> set[str]:
        if not self._current_element_type:
            return set()
        return set(
            self._element_tab_map.get(self._current_element_type.lower(), set())
        )

    def _update_tabs(self, element_type: str | None) -> None:
        normalized = element_type.lower() if element_type else None
        self._current_element_type = normalized
        allowed = set()
        if normalized:
            allowed = set(self._element_tab_map.get(normalized, set()))

        position_widget = self._tab_sections.get("position")
        for name, widget in self._tab_sections.items():
            index = self.tabs.indexOf(widget)
            if index < 0:
                continue
            if name == "position":
                self.tabs.setTabEnabled(index, True)
                continue
            enabled = name in allowed
            self.tabs.setTabEnabled(index, enabled)
            if not enabled and self.tabs.currentWidget() is widget and position_widget:
                self.tabs.setCurrentWidget(position_widget)

        if allowed:
            for name in self._tab_order:
                if name in allowed:
                    target = self._tab_sections.get(name)
                    if target is not None:
                        self.tabs.setCurrentWidget(target)
                    break
        elif position_widget is not None:
            self.tabs.setCurrentWidget(position_widget)

    def _validate_required_fields(self) -> None:
        active_categories = self._active_required_categories()
        for rule in self._required_rules:
            widget = rule["widget"]
            hint = rule["hint"]
            if rule["category"] not in active_categories:
                self._apply_validation_feedback(widget, hint, True)
                continue
            is_valid = rule["validator"]()
            self._apply_validation_feedback(widget, hint, is_valid)

    # ------------------------------------------------------------------
    def set_scene(self, scene: LabelScene | None) -> None:
        if self._scene is not None:
            self._scene.selectionChanged.disconnect(self._on_selection_changed)
        self._disconnect_current_item()
        self._scene = scene
        if scene is not None:
            scene.selectionChanged.connect(self._on_selection_changed)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        scene = self._scene
        if scene is None:
            self.setDisabled(True)
            self._item = None
            self._disconnect_current_item()
            self._update_tabs(None)
            self._validate_required_fields()
            return
        selected = scene.selected_items()
        if not selected:
            self.setDisabled(True)
            self._item = None
            self._disconnect_current_item()
            self._update_tabs(None)
            self._validate_required_fields()
            return
        self.setDisabled(False)
        self._item = selected[0]
        self._disconnect_current_item()
        self._connected_item = self._item
        self._item.propertyChanged.connect(self._on_item_property_changed)
        self._populate_from_item(self._item)

    def _populate_from_item(
        self, item: GraphicsElementItem | TextGraphicsItem
    ) -> None:
        data = item.to_dict()
        element_type = str(data.get("type", "text")).lower()
        name_value = str(data.get("name", ""))
        if not name_value and self._scene is not None:
            name_value = self._scene.default_name(element_type)
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name_value)
        self.name_edit.blockSignals(False)

        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        self.rotation_spin.blockSignals(True)
        self.lock_check.blockSignals(True)
        self.hidden_check.blockSignals(True)

        self.x_spin.setValue(float(data.get("x_mm", 0.0)))
        self.y_spin.setValue(float(data.get("y_mm", 0.0)))
        self.width_spin.setValue(max(1.0, float(data.get("width_mm", 10.0))))
        self.height_spin.setValue(max(1.0, float(data.get("height_mm", 10.0))))
        self.rotation_spin.setValue(float(data.get("rotation", 0.0)))
        self.lock_check.setChecked(bool(data.get("locked", False)))
        self.hidden_check.setChecked(bool(data.get("hidden", False)))

        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)
        self.rotation_spin.blockSignals(False)
        self.lock_check.blockSignals(False)
        self.hidden_check.blockSignals(False)

        self._update_tabs(element_type)

        if element_type == "text":
            font = data.get("font", {}) if isinstance(data.get("font"), dict) else {}
            self.text_content.blockSignals(True)
            self.font_size_spin.blockSignals(True)
            self.bold_check.blockSignals(True)
            self.italic_check.blockSignals(True)
            self.align_combo.blockSignals(True)
            self.font_path_line.blockSignals(True)

            self.text_content.setPlainText(str(data.get("content", "")))
            self.font_size_spin.setValue(int(font.get("size", 24)))
            self.bold_check.setChecked(bool(font.get("bold", False)))
            self.italic_check.setChecked(bool(font.get("italic", False)))
            self.align_combo.setCurrentText(str(data.get("align", "left")))
            ttf_spec = font.get("ttf")
            if isinstance(ttf_spec, Mapping):
                display = str(ttf_spec.get("filename", ""))
            else:
                display = str(ttf_spec or "")
            self.font_path_line.setText(display)

            self.text_content.blockSignals(False)
            self.font_size_spin.blockSignals(False)
            self.bold_check.blockSignals(False)
            self.italic_check.blockSignals(False)
            self.align_combo.blockSignals(False)
            self.font_path_line.blockSignals(False)

        elif element_type == "barcode":
            self.barcode_value.blockSignals(True)
            self.barcode_type.blockSignals(True)
            self.barcode_module.blockSignals(True)
            self.barcode_human.blockSignals(True)

            self.barcode_value.setText(str(data.get("value", "")))
            self.barcode_type.setCurrentText(str(data.get("symbology", "code128")))
            module = float(data.get("module_mm", data.get("module", 0.5)))
            self.barcode_module.setValue(module)
            self.barcode_human.setChecked(bool(data.get("human", True)))

            self.barcode_value.blockSignals(False)
            self.barcode_type.blockSignals(False)
            self.barcode_module.blockSignals(False)
            self.barcode_human.blockSignals(False)

        elif element_type in {"qr", "qrcode"}:
            self.qr_value.blockSignals(True)
            self.qr_error.blockSignals(True)

            self.qr_value.setText(str(data.get("value", "")))
            self.qr_error.setCurrentText(str(data.get("error", "M")).upper())

            self.qr_value.blockSignals(False)
            self.qr_error.blockSignals(False)

        elif element_type == "image":
            self.image_path.blockSignals(True)
            self.image_fit.blockSignals(True)

            self.image_path.setText(str(data.get("source", "")))
            fit_value = data.get("fit", data.get("mode", "contain"))
            self.image_fit.setCurrentText(str(fit_value))

            self.image_path.blockSignals(False)
            self.image_fit.blockSignals(False)

        elif element_type == "shape":
            self.shape_kind.blockSignals(True)
            self.shape_thickness.blockSignals(True)

            self.shape_kind.setCurrentText(str(data.get("kind", "rect")))
            self.shape_thickness.setValue(float(data.get("thickness_mm", 0.4)))

            self.shape_kind.blockSignals(False)
            self.shape_thickness.blockSignals(False)

        self._validate_required_fields()

    # ------------------------------------------------------------------
    def _apply_numeric(self, name: str, value: float) -> None:
        if self._item and self._scene:
            self._scene.change_property(self._item, name, float(value))

    def _commit_name_edit(self) -> None:
        if not self._item or not self._scene:
            return
        proposed = self.name_edit.text().strip()
        element_type = str(self._item.element.get("type", "")).lower()
        unique = self._scene.unique_name(
            proposed,
            element_type=element_type,
            exclude=self._item,
        )
        current = str(self._item.element.get("name", ""))
        if unique != current:
            self._scene.change_property(self._item, "name", unique)
        if unique != self.name_edit.text():
            self.name_edit.blockSignals(True)
            self.name_edit.setText(unique)
            self.name_edit.blockSignals(False)

    def _apply_property(self, name: str, value: Any) -> None:
        if self._item and self._scene:
            self._scene.change_property(self._item, name, value)

    def _on_barcode_value_changed(self, text: str) -> None:
        self._apply_property("value", text)
        self._validate_required_fields()

    def _on_qr_value_changed(self, text: str) -> None:
        self._apply_property("value", text)
        self._validate_required_fields()

    def _apply_font_property(self, name: str, value: Any) -> None:
        if not self._item or not self._scene:
            return
        font = dict(self._item.element.get("font", {}))
        font[name] = value
        self._scene.change_property(self._item, "font", font)

    def _update_font_path(self, text: str) -> None:
        self._apply_font_property("ttf", text or None)

    def _toggle_lock(self, state: bool) -> None:
        if self._item:
            self._item.lock(state)

    def _toggle_hidden(self, state: bool) -> None:
        if self._item:
            self._item.set_hidden(state)

    def _on_text_changed(self) -> None:
        if self._item and self._scene:
            content = self.text_content.toPlainText()
            self._scene.change_property(self._item, "content", content)
        self._validate_required_fields()

    # ------------------------------------------------------------------
    def _update_image_source(self, text: str) -> None:
        self._apply_property("source", text or None)
        self._validate_required_fields()

    def _on_item_property_changed(
        self, item: GraphicsElementItem | TextGraphicsItem, name: str, value: Any
    ) -> None:
        if item is not self._item:
            return
        if name == "name":
            self.name_edit.blockSignals(True)
            self.name_edit.setText(str(value) if value is not None else "")
            self.name_edit.blockSignals(False)
        elif name == "locked":
            self.lock_check.blockSignals(True)
            self.lock_check.setChecked(bool(value))
            self.lock_check.blockSignals(False)
        elif name == "hidden":
            self.hidden_check.blockSignals(True)
            self.hidden_check.setChecked(bool(value))
            self.hidden_check.blockSignals(False)

    def _disconnect_current_item(self) -> None:
        if self._connected_item is not None:
            try:
                self._connected_item.propertyChanged.disconnect(
                    self._on_item_property_changed
                )
            except Exception:  # pragma: no cover - defensive
                pass
            self._connected_item = None

    def _choose_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher fonte",
            str(Path.home()),
            "Fontes (*.ttf *.otf)",
        )
        if path:
            self.font_path_line.setText(path)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher imagem",
            str(Path.home()),
            "Imagens (*.png *.jpg *.jpeg)",
        )
        if path:
            self.image_path.setText(path)
