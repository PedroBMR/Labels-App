"""Standalone window exposing the modern label editor UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from editor.widget import LabelEditorWidget
from model.template import TemplateDocument, TemplateVariable
from printing import (
    Template,
    compile_template,
    recarregar_templates,
    template_manager,
)
from qt_compat import (
    QAction,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QWidget,
    pyqtSignal,
)

__all__ = ["LabelEditorWindow"]


class VariablePanel(QWidget):
    """Panel listing template variables and allowing value editing."""

    changed = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["Variável", "Valor", "Escopo"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout = self.layout() or None
        if layout is None:
            from qt_compat import QVBoxLayout

            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.addWidget(self.table)
        self._variables: dict[str, TemplateVariable] = {}
        self._values: dict[str, Any] = {}
        self.table.itemChanged.connect(self._on_item_changed)

    def set_variables(
        self,
        variables: dict[str, TemplateVariable],
        values: dict[str, Any],
    ) -> None:
        self._variables = dict(variables)
        self._values = dict(values)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for name, var in sorted(self._variables.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            value = values.get(name, "")
            self.table.setItem(row, 1, QTableWidgetItem(str(value)))
            scope_item = QTableWidgetItem(var.scope)
            scope_item.setFlags(scope_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, scope_item)
        self.table.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        name_item = self.table.item(item.row(), 0)
        if not name_item:
            return
        name = name_item.text()
        self._values[name] = item.text()
        self.changed.emit(dict(self._values))

    def values(self) -> dict[str, Any]:
        return dict(self._values)

    def template_values(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, var in self._variables.items():
            if var.scope == "template":
                data[name] = self._values.get(name)
        return data

    def item_values(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, var in self._variables.items():
            if var.scope == "item":
                data[name] = self._values.get(name)
        return data


class LabelEditorWindow(QMainWindow):
    """Standalone window embedding the WYSIWYG label editor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editor de Etiquetas")
        self.resize(1200, 800)
        self.editor = LabelEditorWidget()
        self.setCentralWidget(self.editor)
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.variable_panel = VariablePanel()
        self.variable_panel.changed.connect(self._on_variables_changed)
        self.property_dock = QDockWidget("Propriedades", self)
        self.property_dock.setWidget(self.editor.property_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

        self.variable_dock = QDockWidget("Variáveis", self)
        self.variable_dock.setWidget(self.variable_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.variable_dock)

        self.current_document = TemplateDocument(
            name="Novo",
            page={"backend": "tspl", "width_mm": 80, "height_mm": 60, "dpi": 203},
            elements=[],
            variables={},
        )
        self.current_path: Path | None = None
        self._load_default_template()
        self._build_menus()

    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        file_bar = QToolBar("Arquivo", self)
        self.addToolBar(file_bar)

        new_action = QAction("Novo", self)
        new_action.triggered.connect(self.new_template)
        file_bar.addAction(new_action)

        open_action = QAction("Abrir…", self)
        open_action.triggered.connect(self.open_template)
        file_bar.addAction(open_action)

        save_action = QAction("Salvar", self)
        save_action.triggered.connect(self.save_template)
        file_bar.addAction(save_action)

        save_as_action = QAction("Salvar como…", self)
        save_as_action.triggered.connect(self.save_template_as)
        file_bar.addAction(save_as_action)

        element_bar = QToolBar("Elementos", self)
        self.addToolBar(element_bar)
        add_text = QAction("Texto", self)
        add_text.triggered.connect(lambda: self._add_element("text"))
        element_bar.addAction(add_text)
        add_barcode = QAction("Código de barras", self)
        add_barcode.triggered.connect(lambda: self._add_element("barcode"))
        element_bar.addAction(add_barcode)
        add_qr = QAction("QR Code", self)
        add_qr.triggered.connect(lambda: self._add_element("qr"))
        element_bar.addAction(add_qr)
        add_image = QAction("Imagem", self)
        add_image.triggered.connect(lambda: self._add_element("image"))
        element_bar.addAction(add_image)
        add_shape = QAction("Forma", self)
        add_shape.triggered.connect(lambda: self._add_element("shape"))
        element_bar.addAction(add_shape)

        edit_bar = QToolBar("Editar", self)
        self.addToolBar(edit_bar)
        undo_action = QAction("Desfazer", self)
        undo_action.triggered.connect(self.editor.scene.undo_stack.undo)
        edit_bar.addAction(undo_action)
        redo_action = QAction("Refazer", self)
        redo_action.triggered.connect(self.editor.scene.undo_stack.redo)
        edit_bar.addAction(redo_action)
        align_left = QAction("Alinhar esquerda", self)
        align_left.triggered.connect(self.editor.scene.align_left)
        edit_bar.addAction(align_left)
        align_center = QAction("Alinhar centro", self)
        align_center.triggered.connect(self.editor.scene.align_top)
        edit_bar.addAction(align_center)
        align_right = QAction("Alinhar direita", self)
        align_right.triggered.connect(self.editor.scene.align_right)
        edit_bar.addAction(align_right)
        dist_h = QAction("Distribuir H", self)
        dist_h.triggered.connect(self.editor.scene.distribute_horizontally)
        edit_bar.addAction(dist_h)
        dist_v = QAction("Distribuir V", self)
        dist_v.triggered.connect(self.editor.scene.distribute_vertically)
        edit_bar.addAction(dist_v)

        export_bar = QToolBar("Exportar", self)
        self.addToolBar(export_bar)
        compile_tspl = QAction("Gerar TSPL", self)
        compile_tspl.triggered.connect(self.generate_tspl)
        export_bar.addAction(compile_tspl)
        compile_zpl = QAction("Gerar ZPL", self)
        compile_zpl.triggered.connect(lambda: self.generate_tspl(backend="zpl"))
        export_bar.addAction(compile_zpl)

    # ------------------------------------------------------------------
    def _load_default_template(self) -> None:
        recarregar_templates()
        names = template_manager.list_names()
        document: TemplateDocument
        if names:
            template = template_manager.get_template(names[0])
            document = template.document.copy()
        else:
            document = self.current_document
        self.load_document(document, path=None)

    def load_document(self, document: TemplateDocument, path: Path | None) -> None:
        self.current_document = document.copy()
        self.current_path = path
        self.editor.load_document(self.current_document)
        defaults = self.current_document.defaults(scope="template")
        defaults.update(self.current_document.defaults(scope="item"))
        self.variable_panel.set_variables(self.current_document.variables, defaults)
        self.editor.set_preview_data(defaults)
        self.status.showMessage(f"Modelo: {self.current_document.name}", 3000)

    # ------------------------------------------------------------------
    def new_template(self) -> None:
        document = TemplateDocument(
            name="Novo",
            page={"backend": "tspl", "width_mm": 80, "height_mm": 60, "dpi": 203},
            elements=[],
            variables={},
        )
        self.load_document(document, path=None)

    def open_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir template",
            "",
            "Templates (*.json)",
        )
        if not path:
            return
        try:
            document = TemplateDocument.from_file(path)
        except Exception as exc:  # pragma: no cover - user feedback
            QMessageBox.warning(self, "Erro", f"Falha ao abrir template: {exc}")
            return
        self.load_document(document, Path(path))

    def save_template(self) -> None:
        if not self.current_path:
            self.save_template_as()
            return
        self._write_template(self.current_path)

    def save_template_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar template",
            "",
            "Templates (*.json)",
        )
        if not path:
            return
        self._write_template(Path(path))

    def _write_template(self, path: Path) -> None:
        template = self.editor.to_document(
            self.current_document.name,
            self.current_document.variables,
        )
        self.current_document = template
        template.dump(path)
        self.current_path = path
        self.status.showMessage(f"Template salvo em {path}", 3000)

    # ------------------------------------------------------------------
    def _add_element(self, kind: str) -> None:
        element = self.editor.create_default(kind)
        self.editor.add_element(element)

    def _on_variables_changed(self, values: dict[str, Any]) -> None:
        self.editor.set_preview_data(values)

    # ------------------------------------------------------------------
    def _compile(self, backend: str = "tspl") -> tuple[str, str]:
        template = self.editor.to_document(
            self.current_document.name,
            self.current_document.variables,
        )
        tpl = Template(template)
        template_values = self.variable_panel.template_values()
        item_values = self.variable_panel.item_values()
        variables = dict(template_values)
        variables["items"] = [item_values]
        backend_name, commands = compile_template(tpl, variables, backend_name=backend)
        return backend_name, commands

    def generate_tspl(self, backend: str = "tspl") -> None:
        try:
            backend_name, commands = self._compile(backend)
        except Exception as exc:  # pragma: no cover - user feedback
            QMessageBox.critical(self, "Erro", str(exc))
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle(f"Comandos {backend_name.upper()}")
        dlg.setText(f"Backend: {backend_name}\nTamanho: {len(commands)} bytes")
        dlg.setDetailedText(commands)
        dlg.exec()
