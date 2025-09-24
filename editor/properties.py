"""Property inspector for the label editor."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from qt_compat import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
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
        self._scene: LabelScene | None = None
        self._item: GraphicsElementItem | TextGraphicsItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.general_group = QGroupBox("Posicionamento")
        self.general_form = QFormLayout(self.general_group)

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

        layout.addWidget(self.general_group)

        # --- Text specific -------------------------------------------------
        self.text_group = QGroupBox("Texto")
        self.text_form = QFormLayout(self.text_group)
        self.text_content = QTextEdit()
        self.text_content.setPlaceholderText("Conteúdo com variáveis {exemplo}")
        self.text_content.textChanged.connect(self._on_text_changed)
        self.text_form.addRow(QLabel("Conteúdo"), self.text_content)

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
        font_layout = QVBoxLayout()
        font_layout.addWidget(self.font_path_line)
        font_layout.addWidget(font_button)
        self.text_form.addRow("Arquivo da fonte", font_layout)
        layout.addWidget(self.text_group)

        # --- Barcode -------------------------------------------------------
        self.barcode_group = QGroupBox("Código de barras")
        self.barcode_form = QFormLayout(self.barcode_group)
        self.barcode_value = QLineEdit()
        self.barcode_value.setPlaceholderText("Dados do código")
        self.barcode_value.textChanged.connect(partial(self._apply_property, "value"))
        self.barcode_form.addRow("Dados", self.barcode_value)

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
        layout.addWidget(self.barcode_group)

        # --- QR ------------------------------------------------------------
        self.qr_group = QGroupBox("QR Code")
        self.qr_form = QFormLayout(self.qr_group)
        self.qr_value = QLineEdit()
        self.qr_value.textChanged.connect(partial(self._apply_property, "value"))
        self.qr_form.addRow("Dados", self.qr_value)

        self.qr_error = QComboBox()
        self.qr_error.addItems(["L", "M", "Q", "H"])
        self.qr_error.currentTextChanged.connect(
            partial(self._apply_property, "error")
        )
        self.qr_form.addRow("Correção", self.qr_error)
        layout.addWidget(self.qr_group)

        # --- Image ---------------------------------------------------------
        self.image_group = QGroupBox("Imagem")
        self.image_form = QFormLayout(self.image_group)
        self.image_path = QLineEdit()
        self.image_path.textChanged.connect(self._update_image_source)
        self.image_button = QPushButton("Escolher…")
        self.image_button.clicked.connect(self._choose_image)
        image_layout = QVBoxLayout()
        image_layout.addWidget(self.image_path)
        image_layout.addWidget(self.image_button)
        self.image_form.addRow("Arquivo", image_layout)

        self.image_fit = QComboBox()
        self.image_fit.addItems(["contain", "cover"])
        self.image_fit.currentTextChanged.connect(partial(self._apply_property, "fit"))
        self.image_form.addRow("Ajuste", self.image_fit)
        layout.addWidget(self.image_group)

        # --- Shape ---------------------------------------------------------
        self.shape_group = QGroupBox("Formas")
        self.shape_form = QFormLayout(self.shape_group)
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
        layout.addWidget(self.shape_group)

        layout.addStretch(1)
        self.setDisabled(True)

    # ------------------------------------------------------------------
    def set_scene(self, scene: LabelScene | None) -> None:
        if self._scene is not None:
            self._scene.selectionChanged.disconnect(self._on_selection_changed)
        self._scene = scene
        if scene is not None:
            scene.selectionChanged.connect(self._on_selection_changed)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        scene = self._scene
        if scene is None:
            self.setDisabled(True)
            self._item = None
            return
        selected = scene.selected_items()
        if not selected:
            self.setDisabled(True)
            self._item = None
            return
        self.setDisabled(False)
        self._item = selected[0]
        self._populate_from_item(self._item)

    def _populate_from_item(
        self, item: GraphicsElementItem | TextGraphicsItem
    ) -> None:
        data = item.to_dict()
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

        element_type = str(data.get("type", "text")).lower()
        self._show_groups(element_type)

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
            self.font_path_line.setText(str(font.get("ttf", "")))

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

    # ------------------------------------------------------------------
    def _show_groups(self, element_type: str) -> None:
        self.text_group.hide()
        self.barcode_group.hide()
        self.qr_group.hide()
        self.image_group.hide()
        self.shape_group.hide()
        if element_type == "text":
            self.text_group.show()
        elif element_type == "barcode":
            self.barcode_group.show()
        elif element_type in {"qr", "qrcode"}:
            self.qr_group.show()
        elif element_type == "image":
            self.image_group.show()
        elif element_type == "shape":
            self.shape_group.show()

    # ------------------------------------------------------------------
    def _apply_numeric(self, name: str, value: float) -> None:
        if self._item and self._scene:
            self._scene.change_property(self._item, name, float(value))

    def _apply_property(self, name: str, value: Any) -> None:
        if self._item and self._scene:
            self._scene.change_property(self._item, name, value)

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

    # ------------------------------------------------------------------
    def _update_image_source(self, text: str) -> None:
        self._apply_property("source", text or None)

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
