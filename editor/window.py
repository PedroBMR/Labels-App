"""Standalone window exposing the modern label editor UI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from editor.widget import LabelEditorWidget
from model.template import TemplateDocument
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
    QInputDialog,
    QKeySequence,
    QMainWindow,
    QMessageBox,
    QSettings,
    QStatusBar,
    Qt,
    QTimer,
    QToolBar,
    QWidget,
)
from ui.tour import GuidedTourDialog, TourStep
from .variables import VariablePanel
from template_store import template_store

__all__ = ["LabelEditorWindow"]


_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*$")


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
        self._settings = QSettings("CONIMS", "LabelEditor")
        self._loading_state = False
        self._in_compact_transition = False
        self._normal_splitter_sizes: list[int] | None = None
        self._compact_splitter_sizes: list[int] | None = None
        self._dock_visibility_cache: dict[str, bool] = {}

        self.file_toolbar: QToolBar | None = None
        self.element_toolbar: QToolBar | None = None
        self.edit_toolbar: QToolBar | None = None
        self.export_toolbar: QToolBar | None = None

        self._tour_action = QAction("Tour guiado", self)
        self._tour_action.setShortcut(QKeySequence("Shift+F1"))
        self._tour_action.triggered.connect(lambda: self._show_guided_tour(force=True))

        self.variable_panel = VariablePanel()
        self.variable_panel.changed.connect(self._on_variables_changed)
        self.property_dock = QDockWidget("Propriedades", self)
        self.property_dock.setWidget(self.editor.property_panel)
        self.property_dock.setObjectName("propertiesDock")
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

        self.variable_dock = QDockWidget("Variáveis", self)
        self.variable_dock.setWidget(self.variable_panel)
        self.variable_dock.setObjectName("variablesDock")
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
        self._tour_shown = False
        QTimer.singleShot(200, self._show_guided_tour)
        self.addAction(self.compact_action)
        self.addAction(self.fullscreen_action)
        self.addAction(self.reset_splitter_action)
        self.addAction(self._tour_action)
        self.editor.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.property_dock.visibilityChanged.connect(
            lambda visible, dock=self.property_dock: self._save_dock_state(dock, visible)
        )
        self.variable_dock.visibilityChanged.connect(
            lambda visible, dock=self.variable_dock: self._save_dock_state(dock, visible)
        )
        QTimer.singleShot(0, self._restore_state)

    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        file_bar = QToolBar("Arquivo", self)
        self.addToolBar(file_bar)
        self.file_toolbar = file_bar

        new_action = QAction("Novo", self)
        new_action.triggered.connect(self.new_template)
        file_bar.addAction(new_action)

        create_action = QAction("Create Label", self)
        create_action.triggered.connect(self.create_label)
        file_bar.addAction(create_action)

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
        self.element_toolbar = element_bar
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
        self.edit_toolbar = edit_bar
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
        self.export_toolbar = export_bar
        compile_tspl = QAction("Gerar TSPL", self)
        compile_tspl.triggered.connect(self.generate_tspl)
        export_bar.addAction(compile_tspl)
        compile_zpl = QAction("Gerar ZPL", self)
        compile_zpl.triggered.connect(lambda: self.generate_tspl(backend="zpl"))
        export_bar.addAction(compile_zpl)

        view_menu = self.menuBar().addMenu("Exibir")
        self.compact_action = QAction("Modo compacto", self)
        self.compact_action.setCheckable(True)
        self.compact_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.compact_action.toggled.connect(self._on_compact_toggled)
        view_menu.addAction(self.compact_action)

        self.fullscreen_action = QAction("Alternar tela cheia", self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self.fullscreen_action)

        self.reset_splitter_action = QAction("Restaurar divisória (50/50)", self)
        self.reset_splitter_action.setShortcut(QKeySequence("Ctrl+0"))
        self.reset_splitter_action.triggered.connect(self._reset_splitter)
        view_menu.addAction(self.reset_splitter_action)

        view_menu.addSeparator()
        view_menu.addAction(self.property_dock.toggleViewAction())
        view_menu.addAction(self.variable_dock.toggleViewAction())

        help_menu = self.menuBar().addMenu("Ajuda")
        help_menu.addAction(self._tour_action)

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

    def create_label(self) -> None:
        width = float(self.current_document.page.get("width_mm", 80) or 80)
        height = float(self.current_document.page.get("height_mm", 60) or 60)
        default_text = f"{width:g}x{height:g}"
        text, ok = QInputDialog.getText(
            self,
            "Create Label",
            "Informe o tamanho (Largura x Altura, em mm):",
            text=default_text,
        )
        if not ok:
            return
        cleaned = text.strip()
        match = _SIZE_RE.match(cleaned)
        if not match:
            QMessageBox.warning(
                self,
                "Tamanho inválido",
                "Use o formato largura x altura, por exemplo 100x30.",
            )
            return
        width_value = float(match.group(1).replace(",", "."))
        height_value = float(match.group(2).replace(",", "."))
        if width_value <= 0 or height_value <= 0:
            QMessageBox.warning(
                self,
                "Tamanho inválido",
                "As dimensões devem ser maiores que zero.",
            )
            return

        base_page = dict(self.current_document.page)
        base_page["width_mm"] = width_value
        base_page["height_mm"] = height_value
        base_page.setdefault("backend", base_page.get("type", "tspl"))
        base_page.setdefault("dpi", 203)

        name = f"{width_value:g}x{height_value:g}"
        document = TemplateDocument(
            name=name,
            page=base_page,
            elements=[],
            variables={},
        )
        self.load_document(document, path=None)
        self.status.showMessage(
            f"Etiqueta {width_value:g}x{height_value:g} criada", 4000
        )

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
        target = self._ensure_in_templates(self.current_path)
        overwrite = target == self.current_path
        if target.exists() and not overwrite:
            reply = QMessageBox.question(
                self,
                "Sobrescrever modelo?",
                "Já existe um modelo salvo com esse nome. Deseja substituí-lo?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            overwrite = True
        self._write_template(target, overwrite=overwrite)

    def save_template_as(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Salvar modelo",
            "Nome do modelo:",
            text=self.current_document.name or "Novo",
        )
        if not ok:
            return
        cleaned = name.strip()
        if not cleaned:
            QMessageBox.warning(
                self,
                "Nome inválido",
                "Informe um nome para o modelo antes de salvar.",
            )
            return
        self.current_document.name = cleaned
        target = self._path_for_name(cleaned)
        overwrite = target == self.current_path or not target.exists()
        if target.exists() and target != self.current_path:
            reply = QMessageBox.question(
                self,
                "Sobrescrever modelo?",
                "Já existe um modelo salvo com esse nome. Deseja substituí-lo?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            overwrite = True
        self._write_template(target, overwrite=overwrite)

    def _ensure_document_name(self) -> str:
        name = (self.current_document.name or "").strip()
        if not name:
            name = "Modelo"
            self.current_document.name = name
        return name

    def _path_for_name(self, name: str) -> Path:
        return template_store.path_for_name(name)

    def _ensure_in_templates(self, path: Path) -> Path:
        fallback = (self.current_document.name or "").strip() or path.stem or "Modelo"
        self.current_document.name = fallback
        return template_store.ensure_path(path, name=fallback)

    def _write_template(self, path: Path, *, overwrite: bool = False) -> None:
        target = self._ensure_in_templates(path)
        if target.exists() and target != self.current_path and not overwrite:
            QMessageBox.warning(
                self,
                "Arquivo existente",
                "Já existe um arquivo com esse nome. Escolha outro nome para o modelo.",
            )
            return
        name = self._ensure_document_name()
        self.editor.update_preview(immediate=True)
        template = self.editor.to_document(
            name,
            self.current_document.variables,
        )
        self.current_document = template
        is_same_file = (
            self.current_path is not None and Path(self.current_path) == target
        )
        try:
            saved_path = template_store.save(
                template,
                path=target,
                overwrite=overwrite or is_same_file,
            )
        except FileExistsError:
            QMessageBox.warning(
                self,
                "Arquivo existente",
                "Já existe um arquivo com esse nome. Escolha outro nome para o modelo.",
            )
            return
        except OSError as exc:  # pragma: no cover - feedback ao usuário
            QMessageBox.critical(
                self,
                "Erro",
                f"Não foi possível salvar o modelo: {exc}",
            )
            return
        self.current_path = saved_path
        self.status.showMessage(f"Template salvo em {saved_path}", 3000)

    # ------------------------------------------------------------------
    def _show_guided_tour(self, force: bool = False) -> None:
        if not force and self._tour_shown:
            return
        skip_onboarding = bool(self._settings.value("onboarding/skip", False, type=bool))
        if not force and skip_onboarding:
            return

        steps = self._build_tour_steps()
        if not steps:
            self._tour_shown = True
            return

        dialog = GuidedTourDialog(self, steps, dont_show_checked=skip_onboarding)
        dialog.exec()
        if dialog.dont_show_again:
            self._settings.setValue("onboarding/skip", True)
        elif force:
            self._settings.setValue("onboarding/skip", False)
        self._tour_shown = True

    def _build_tour_steps(self) -> list[TourStep]:
        steps: list[TourStep] = [
            TourStep(
                title="Bem-vindo ao editor",
                body=(
                    "Este tour destaca as principais áreas para começar rapidamente. "
                    "Use Enter ou Espaço para avançar."
                ),
                anchor=None,
                highlight_padding=0,
            )
        ]

        if self.file_toolbar is not None:
            steps.append(
                TourStep(
                    title="Barras de ferramentas",
                    body=(
                        "As barras superiores concentram ações para criar modelos, "
                        "inserir elementos e exportar seu trabalho. O atalho "
                        "Create Label abre um novo rótulo no tamanho desejado."
                    ),
                    anchor=self.file_toolbar,
                    highlight_padding=24,
                )
            )

        steps.append(
            TourStep(
                title="Canvas de edição",
                body=(
                    "Arraste os elementos diretamente sobre o canvas para reposicioná-los. "
                    "Use Ctrl + rolagem do mouse para ajustar o zoom e Espaço para arrastar a área visível."
                ),
                anchor=self.editor.view,
                highlight_padding=28,
            )
        )

        steps.append(
            TourStep(
                title="Painéis de propriedades",
                body=(
                    "Selecione um item para ajustar fonte, cores e alinhamento neste painel lateral. "
                    "A aba Variáveis permite informar os valores dinâmicos usados no modelo."
                ),
                anchor=self.property_dock,
                highlight_padding=20,
            )
        )

        steps.append(
            TourStep(
                title="Pré-visualização",
                body=(
                    "A pré-visualização renderiza o resultado final com os dados atuais. "
                    "Ajuste o zoom pelos controles inferiores para conferir os detalhes antes de exportar."
                ),
                anchor=self.editor.preview_widget,
                highlight_padding=28,
            )
        )

        return [step for step in steps if step.anchor is None or step.anchor.isVisible()]

    # ------------------------------------------------------------------
    def _add_element(self, kind: str) -> None:
        element = self.editor.create_default(kind)
        self.editor.add_element(element)

    def _on_variables_changed(self, values: dict[str, Any]) -> None:
        self.editor.set_preview_data(values)

    def _on_compact_toggled(self, checked: bool) -> None:
        self._set_compact_mode(checked)

    def _set_compact_mode(self, enabled: bool, *, restoring: bool = False) -> None:
        if self._loading_state and not restoring:
            return
        if enabled:
            if not self._normal_splitter_sizes:
                self._normal_splitter_sizes = self.editor.splitter.sizes()
            if not restoring and self._normal_splitter_sizes:
                self._write_sizes("ui/splitSizes/normal", self._normal_splitter_sizes)
            self._dock_visibility_cache = {
                "propertiesDock": self.property_dock.isVisible(),
                "variablesDock": self.variable_dock.isVisible(),
            }
            self._in_compact_transition = True
            self.property_dock.hide()
            self.variable_dock.hide()
            self._in_compact_transition = False
            sizes = self._compact_splitter_sizes
            if not sizes:
                base = self._normal_splitter_sizes or self.editor.splitter.sizes()
                total = sum(base)
                if total <= 0:
                    total = max(self.editor.width(), 2)
                preview = max(1, int(round(total * 0.35)))
                canvas = max(1, total - preview)
                sizes = [canvas, preview]
            self.editor.splitter.setSizes(sizes)
            if not restoring:
                self._write_sizes("ui/splitSizes/compact", sizes)
                self._settings.setValue("ui/compact", True)
                self._settings.setValue(
                    "ui/docks/propertiesDock",
                    bool(self._dock_visibility_cache.get("propertiesDock", True)),
                )
                self._settings.setValue(
                    "ui/docks/variablesDock",
                    bool(self._dock_visibility_cache.get("variablesDock", True)),
                )
        else:
            self._compact_splitter_sizes = self.editor.splitter.sizes()
            cache = self._dock_visibility_cache or {
                "propertiesDock": self._read_bool("ui/docks/propertiesDock", True),
                "variablesDock": self._read_bool("ui/docks/variablesDock", True),
            }
            self._in_compact_transition = True
            self.property_dock.setVisible(cache.get("propertiesDock", True))
            self.variable_dock.setVisible(cache.get("variablesDock", True))
            self._in_compact_transition = False
            self._dock_visibility_cache = {}
            sizes = self._normal_splitter_sizes
            if sizes and sum(sizes) > 0:
                self.editor.splitter.setSizes(sizes)
            else:
                total = max(self.editor.width(), 2)
                left = total // 2
                self.editor.splitter.setSizes([left, total - left])
            if not restoring:
                self._write_sizes("ui/splitSizes/normal", self.editor.splitter.sizes())
                self._settings.setValue(
                    "ui/docks/propertiesDock", bool(cache.get("propertiesDock", True))
                )
                self._settings.setValue(
                    "ui/docks/variablesDock", bool(cache.get("variablesDock", True))
                )
                self._settings.setValue("ui/compact", False)

    def _reset_splitter(self) -> None:
        sizes = self.editor.splitter.sizes()
        total = sum(sizes)
        if total <= 0:
            total = max(self.editor.width(), 2)
        left = total // 2
        self.editor.splitter.setSizes([left, total - left])
        self._on_splitter_moved()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            sizes = (
                self._compact_splitter_sizes
                if self.compact_action.isChecked()
                else self._normal_splitter_sizes
            )
            if sizes:
                QTimer.singleShot(0, lambda s=list(sizes): self.editor.splitter.setSizes(s))
        else:
            current = self.editor.splitter.sizes()
            if self.compact_action.isChecked():
                self._compact_splitter_sizes = current
            else:
                self._normal_splitter_sizes = current
            self.showFullScreen()

    def _on_splitter_moved(self, *_args: object) -> None:
        if self._loading_state:
            return
        sizes = self.editor.splitter.sizes()
        if self.compact_action.isChecked():
            self._compact_splitter_sizes = sizes
            self._write_sizes("ui/splitSizes/compact", sizes)
        else:
            self._normal_splitter_sizes = sizes
            self._write_sizes("ui/splitSizes/normal", sizes)

    def _save_dock_state(self, dock: QDockWidget, visible: bool) -> None:
        if self._loading_state or self._in_compact_transition:
            return
        key = f"ui/docks/{dock.objectName() or dock.windowTitle()}"
        self._settings.setValue(key, bool(visible))

    def _write_sizes(self, key: str, sizes: list[int]) -> None:
        if not sizes:
            return
        self._settings.setValue(key, ",".join(str(int(max(0, value))) for value in sizes))

    def _read_sizes(self, key: str) -> list[int] | None:
        value = self._settings.value(key)
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            raw = value
        else:
            raw = str(value).split(",")
        sizes: list[int] = []
        for part in raw:
            try:
                sizes.append(int(round(float(part))))
            except (TypeError, ValueError):
                continue
        return sizes or None

    def _read_bool(self, key: str, default: bool) -> bool:
        value = self._settings.value(key)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).lower() in {"1", "true", "yes"}

    def _restore_state(self) -> None:
        self._loading_state = True
        try:
            self._normal_splitter_sizes = self._read_sizes("ui/splitSizes/normal")
            self._compact_splitter_sizes = self._read_sizes("ui/splitSizes/compact")
            prop_visible = self._read_bool("ui/docks/propertiesDock", True)
            var_visible = self._read_bool("ui/docks/variablesDock", True)
            self.property_dock.setVisible(prop_visible)
            self.variable_dock.setVisible(var_visible)
            compact_enabled = self._read_bool("ui/compact", False)
            if compact_enabled:
                self.compact_action.blockSignals(True)
                self.compact_action.setChecked(True)
                self.compact_action.blockSignals(False)
                self._set_compact_mode(True, restoring=True)
            else:
                self.compact_action.setChecked(False)
                if self._normal_splitter_sizes:
                    self.editor.splitter.setSizes(self._normal_splitter_sizes)
        finally:
            self._loading_state = False

    def _save_state(self) -> None:
        if self.compact_action.isChecked():
            self._write_sizes("ui/splitSizes/compact", self.editor.splitter.sizes())
            if self._normal_splitter_sizes:
                self._write_sizes("ui/splitSizes/normal", self._normal_splitter_sizes)
            prop_visible = self._dock_visibility_cache.get(
                "propertiesDock", self._read_bool("ui/docks/propertiesDock", True)
            )
            var_visible = self._dock_visibility_cache.get(
                "variablesDock", self._read_bool("ui/docks/variablesDock", True)
            )
        else:
            self._write_sizes("ui/splitSizes/normal", self.editor.splitter.sizes())
            prop_visible = self.property_dock.isVisible()
            var_visible = self.variable_dock.isVisible()
        self._settings.setValue("ui/compact", self.compact_action.isChecked())
        self._settings.setValue("ui/docks/propertiesDock", bool(prop_visible))
        self._settings.setValue("ui/docks/variablesDock", bool(var_visible))

    def closeEvent(self, event) -> None:  # noqa: D401
        self._save_state()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    def _compile(self, backend: str = "tspl") -> tuple[str, bytes]:
        self.editor.update_preview(immediate=True)
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
        dlg.setDetailedText(commands.decode("latin-1", errors="replace"))
        dlg.exec()
