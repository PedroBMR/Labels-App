"""Interface gráfica do editor de etiquetas."""
from __future__ import annotations

import os
import re
from typing import Any, Callable

from _version import __version__
from editor import LabelScene, LabelView
from editor.items import (
    BarcodeLabelItem,
    BaseLabelItem,
    ImageLabelItem,
    QRLabelItem,
    ShapeLabelItem,
    TextLabelItem,
)
from editor.properties import PropertyInspector
from log import LOG_FILE, logger, register_status_callback
from persistence import carregar_config, salvar_config
from printing import (
    DEFAULT_LABEL_TEXTS,
    LABEL_FIELDS,
    aplicar_template,
    listar_impressoras,
    listar_templates,
)
from printing_utils import FONT_BASE_W, text_width_dots
from render.preview import PreviewRenderer
from utils import backup_automatico, recurso_caminho

from qt_compat import (
    QAction,
    QCheckBox,
    QColor,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPointF,
    QTime,
    QTimeEdit,
    QTimer,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QUndoStack,
    Qt,
    QSize,
    QSizePolicy,
)


_PLACEHOLDER_PATTERN = re.compile(r"{([^{}]+)}")


def _extract_placeholders() -> list[str]:
    found: set[str] = set()
    for text in DEFAULT_LABEL_TEXTS.values():
        for match in _PLACEHOLDER_PATTERN.findall(text):
            found.add("{" + match + "}")
    return sorted(found)


_PLACEHOLDERS = _extract_placeholders()
_FONT_SIZE_MAP = {"1": 8.0, "2": 10.0, "3": 12.0, "4": 16.0, "5": 22.0, "6": 28.0}


class ConfigDialog(QDialog):
    """Janela de configurações básicas do editor."""

    def __init__(self, parent: QWidget | None, settings: dict[str, Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self._settings = settings

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.printer_combo = QComboBox()
        self.printer_combo.setEditable(True)
        form.addRow("Impressora padrão:", self.printer_combo)

        self.template_combo = QComboBox()
        self.template_combo.setEditable(False)
        form.addRow("Modelo padrão:", self.template_combo)

        self.backup_time = QTimeEdit()
        self.backup_time.setDisplayFormat("HH:mm")
        form.addRow("Horário do backup:", self.backup_time)

        layout.addLayout(form)

        self.retry_checkbox = QCheckBox("Repetir impressão automaticamente (3x)")
        layout.addWidget(self.retry_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self) -> None:
        printers = listar_impressoras()
        current_printer = str(self._settings.get("ultima_impressora", ""))
        if printers:
            self.printer_combo.addItems(printers)
        if current_printer:
            index = self.printer_combo.findText(current_printer)
            if index < 0:
                self.printer_combo.addItem(current_printer)
                index = self.printer_combo.count() - 1
            self.printer_combo.setCurrentIndex(index)

        templates = listar_templates()
        self.template_combo.addItems(templates)
        current_template = str(
            self._settings.get("template_editor")
            or self._settings.get("template_atual")
            or ""
        )
        if current_template:
            index = self.template_combo.findText(current_template)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)

        time_text = str(self._settings.get("backup_horario", "17:10"))
        time = QTime.fromString(time_text, "HH:mm")
        if not time.isValid():
            time = QTime(17, 10)
        self.backup_time.setTime(time)

        self.retry_checkbox.setChecked(bool(self._settings.get("retry_automatico")))

    def accept(self) -> None:  # noqa: D401 - Qt API
        self._settings["ultima_impressora"] = self.printer_combo.currentText().strip()
        template = self.template_combo.currentText().strip()
        if template:
            self._settings["template_editor"] = template
        self._settings["backup_horario"] = self.backup_time.time().toString("HH:mm")
        self._settings["retry_automatico"] = self.retry_checkbox.isChecked()
        super().accept()

    def result_settings(self) -> dict[str, Any]:
        return self._settings


class EtiquetaApp(QMainWindow):
    """Janela principal do editor de etiquetas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Gerador de Etiquetas CONIMS")
        self.resize(1200, 800)

        icon_path = recurso_caminho("color.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.config = carregar_config()
        self.scene = LabelScene()
        self.undo_stack = QUndoStack(self)
        self.scene.set_undo_stack(self.undo_stack)
        self.view = LabelView(self.scene)
        self.property_dock = PropertyInspector(self)
        self.property_dock.bind_scene(self.scene)
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(260, 260)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background:#1e1e1e;border:1px solid #333;")
        self.preview_renderer = PreviewRenderer(self.scene, self.preview_label, self.scene.dpi)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.view, stretch=3)

        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)
        preview_label = QLabel("Pré-visualização")
        preview_label.setStyleSheet("color:#dddddd;font-weight:600;")
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.preview_label, stretch=1)
        layout.addLayout(preview_layout, stretch=1)

        self.setCentralWidget(central)

        self.statusBar().showMessage("Editor pronto")
        register_status_callback(self._status_message)

        self._placeholders = _PLACEHOLDERS
        self._loading_templates = False
        self._printer_refresh_timer: QTimer | None = None
        self._current_template_name: str | None = None

        self._create_toolbar()
        self._create_menus()
        self._apply_editor_preferences()

        QTimer.singleShot(0, self._initialize_editor)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Ferramentas", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        undo_action = self.undo_stack.createUndoAction(self, "Desfazer")
        undo_action.setShortcut("Ctrl+Z")
        toolbar.addAction(undo_action)

        redo_action = self.undo_stack.createRedoAction(self, "Refazer")
        redo_action.setShortcut("Ctrl+Shift+Z")
        toolbar.addAction(redo_action)

        toolbar.addSeparator()

        alignments = [
            ("⯇", "Alinhar à esquerda", lambda: self._align_selected("left")),
            ("⇔", "Alinhar ao centro", lambda: self._align_selected("center")),
            ("⯈", "Alinhar à direita", lambda: self._align_selected("right")),
            ("⯅", "Alinhar ao topo", lambda: self._align_selected("top")),
            ("⇕", "Alinhar ao meio", lambda: self._align_selected("middle")),
            ("⯆", "Alinhar à base", lambda: self._align_selected("bottom")),
        ]
        for text, tip, slot in alignments:
            action = QAction(text, self)
            action.setToolTip(tip)
            action.triggered.connect(slot)
            toolbar.addAction(action)

        toolbar.addSeparator()

        distribute_h = QAction("⇤⇥", self)
        distribute_h.setToolTip("Distribuir horizontalmente")
        distribute_h.triggered.connect(lambda: self._distribute_selected("horizontal"))
        toolbar.addAction(distribute_h)

        distribute_v = QAction("⇑⇓", self)
        distribute_v.setToolTip("Distribuir verticalmente")
        distribute_v.triggered.connect(lambda: self._distribute_selected("vertical"))
        toolbar.addAction(distribute_v)

        toolbar.addSeparator()

        self.grid_action = QAction("Grade", self)
        self.grid_action.setCheckable(True)
        self.grid_action.triggered.connect(self._toggle_grid)
        toolbar.addAction(self.grid_action)

        self.snap_action = QAction("Ajustar à grade", self)
        self.snap_action.setCheckable(True)
        self.snap_action.triggered.connect(self._toggle_snap)
        toolbar.addAction(self.snap_action)

        toolbar.addSeparator()

        zoom_in = QAction("+", self)
        zoom_in.setToolTip("Aproximar")
        zoom_in.setShortcut("Ctrl++")
        zoom_in.triggered.connect(self._zoom_in)
        toolbar.addAction(zoom_in)

        zoom_out = QAction("-", self)
        zoom_out.setToolTip("Afastar")
        zoom_out.setShortcut("Ctrl+-")
        zoom_out.triggered.connect(self._zoom_out)
        toolbar.addAction(zoom_out)

        zoom_reset = QAction("100%", self)
        zoom_reset.setToolTip("Zoom normal")
        zoom_reset.triggered.connect(self._zoom_reset)
        toolbar.addAction(zoom_reset)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(50)
        toolbar.addWidget(self._zoom_label)

        toolbar.addSeparator()

        placeholder_label = QLabel("Variáveis:")
        placeholder_label.setStyleSheet("color:#cccccc;")
        toolbar.addWidget(placeholder_label)

        self.placeholder_combo = QComboBox()
        self.placeholder_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.placeholder_combo.addItem("Inserir variável…")
        for placeholder in self._placeholders:
            self.placeholder_combo.addItem(placeholder)
        self.placeholder_combo.currentIndexChanged.connect(self._placeholder_selected)
        toolbar.addWidget(self.placeholder_combo)

        toolbar.addSeparator()

        model_label = QLabel("Modelo:")
        model_label.setStyleSheet("color:#cccccc;")
        toolbar.addWidget(model_label)

        self.template_combo = QComboBox()
        self.template_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.template_combo.currentTextChanged.connect(self._on_template_changed)
        toolbar.addWidget(self.template_combo)

    def _create_menus(self) -> None:
        arquivo = self.menuBar().addMenu("&Arquivo")
        arquivo.addAction("Configurações…", self._abrir_config)
        arquivo.addSeparator()
        arquivo.addAction("Fechar", self.close)

        ajuda = self.menuBar().addMenu("&Ajuda")
        ajuda.addAction("Sobre", self._mostrar_sobre)

    def _apply_editor_preferences(self) -> None:
        grid_visible = bool(self.config.get("editor_grid_visible", True))
        snap = bool(self.config.get("editor_snap", True))
        grid_mm = float(self.config.get("editor_grid_mm", 1.0))
        self.scene.set_grid_visible(grid_visible)
        self.scene.set_snap_to_grid(snap)
        self.scene.set_grid_mm(grid_mm)
        self.grid_action.setChecked(grid_visible)
        self.snap_action.setChecked(snap)

    def _initialize_editor(self) -> None:
        self._load_template_names()
        stored_template = str(
            self.config.get("template_editor")
            or self.config.get("template_atual")
            or (self.template_combo.itemText(0) if self.template_combo.count() else "")
        )
        if stored_template:
            index = self.template_combo.findText(stored_template)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        if self.template_combo.count():
            self._load_template(self.template_combo.currentText())
        self._printer_refresh_timer = QTimer(self)
        self._printer_refresh_timer.setInterval(60000)
        self._printer_refresh_timer.timeout.connect(self._verificar_impressora)
        self._verificar_impressora()
        self._printer_refresh_timer.start()

    def _load_template_names(self) -> None:
        self._loading_templates = True
        self.template_combo.clear()
        for name in listar_templates():
            self.template_combo.addItem(name)
        self._loading_templates = False

    def _on_template_changed(self, name: str) -> None:
        if self._loading_templates:
            return
        if not name:
            return
        self._load_template(name)

    def _load_template(self, name: str) -> None:
        try:
            template = aplicar_template(name)
        except Exception as exc:  # pragma: no cover - feedback visual
            logger.exception("Falha ao aplicar template '%s'", name)
            QMessageBox.critical(self, "Erro", f"Não foi possível carregar o modelo '{name}'.\n{exc}")
            return

        self._current_template_name = name
        self.scene.set_template_rect(template.largura_mm, template.altura_mm)
        self.scene.clear_label_items()
        self.undo_stack.clear()
        self._populate_from_template(template)
        self.view.zoom_reset()
        self.view.centerOn(self.scene.sceneRect().center())
        self._update_zoom_label()
        self.preview_renderer.schedule()
        self.statusBar().showMessage(f"Modelo '{name}' carregado")
        self.config["template_editor"] = name
        salvar_config(self.config)

    def _font_size_for_code(self, font_code: str) -> float:
        return _FONT_SIZE_MAP.get(str(font_code), 12.0)

    def _populate_from_template(self, template) -> None:
        margin = self.scene.mm_to_dots(3.0)
        for field in LABEL_FIELDS:
            info = template.layout.get(field)
            if not isinstance(info, dict):
                continue
            text = DEFAULT_LABEL_TEXTS.get(field, field.upper())
            font_code = str(info.get("font", "2"))
            xm = int(info.get("xm", 1))
            ym = int(info.get("ym", 1))
            base_width = text_width_dots(text, font_code, xm)
            base_height = FONT_BASE_W.get(font_code, 12) * max(1, ym)
            width = max(self.scene.mm_to_dots(20.0), base_width * 1.2)
            height = max(self.scene.mm_to_dots(6.0), base_height * 1.4)
            item = TextLabelItem(
                text=text,
                size=(width, height),
                font_size=self._font_size_for_code(font_code),
            )
            item.setPos(float(info.get("x", 0)), float(info.get("y", 0)))
            self.scene.addItem(item)

        scene_rect = self.scene.sceneRect()
        width = scene_rect.width()
        height = scene_rect.height()

        barcode_item = BarcodeLabelItem(
            data="{saida}",
            size=(max(width * 0.35, 220.0), max(height * 0.18, 60.0)),
        )
        barcode_item.setPos(margin, height - barcode_item.rect().height() - margin)
        self.scene.addItem(barcode_item)

        qr_size = max(min(width, height) * 0.22, 90.0)
        qr_item = QRLabelItem(data="{saida}", size=(qr_size, qr_size))
        qr_item.setPos(width - qr_size - margin, height - qr_size - margin)
        self.scene.addItem(qr_item)

        image_item = ImageLabelItem(size=(max(width * 0.2, 160.0), max(height * 0.2, 120.0)))
        image_item.setPos(width - image_item.rect().width() - margin, margin)
        self.scene.addItem(image_item)

        shape_item = ShapeLabelItem(
            size=(max(width * 0.6, 300.0), max(height * 0.15, 80.0)),
            shape="rounded",
            fill=None,
            stroke=QColor(80, 80, 80),
            stroke_width=2.0,
            corner_radius=12.0,
        )
        shape_item.setPos(margin, height * 0.45)
        shape_item.setZValue(-5)
        self.scene.addItem(shape_item)

        self.scene.clearSelection()

    def _placeholder_selected(self, index: int) -> None:
        if index <= 0:
            return
        placeholder = self.placeholder_combo.itemText(index)
        self.placeholder_combo.blockSignals(True)
        self.placeholder_combo.setCurrentIndex(0)
        self.placeholder_combo.blockSignals(False)
        self._insert_placeholder(placeholder)

    def _insert_placeholder(self, placeholder: str) -> None:
        targets = [
            item for item in self.scene.selected_label_items() if isinstance(item, TextLabelItem)
        ]
        if not targets:
            self.statusBar().showMessage("Selecione um item de texto para inserir variáveis.", 4000)
            return
        for item in targets:
            self._apply_item_change(
                item,
                lambda it=item: it.set_text(it.text() + placeholder),
                f"Inserir {placeholder}",
            )

    def _apply_item_change(
        self, item: BaseLabelItem, operation: Callable[[], None], description: str
    ) -> None:
        scene = self.scene
        before = scene.capture_item_state(item)
        item.blockSignals(True)
        try:
            operation()
        finally:
            item.blockSignals(False)
        item.notify_geometry_changed()
        after = scene.capture_item_state(item)
        scene.push_state(item, before, after, description)

    def _align_selected(self, mode: str) -> None:
        items = self.scene.selected_label_items()
        if len(items) < 2:
            return
        rects = [item.mapToScene(item.boundingRect()).boundingRect() for item in items]
        before = [self.scene.capture_item_state(item) for item in items]

        def apply_alignment() -> None:
            if mode == "left":
                target = min(r.left() for r in rects)
                deltas = [target - r.left() for r in rects]
                vectors = [QPointF(delta, 0.0) for delta in deltas]
            elif mode == "right":
                target = max(r.right() for r in rects)
                deltas = [target - r.right() for r in rects]
                vectors = [QPointF(delta, 0.0) for delta in deltas]
            elif mode == "center":
                target = sum(r.center().x() for r in rects) / len(rects)
                deltas = [target - r.center().x() for r in rects]
                vectors = [QPointF(delta, 0.0) for delta in deltas]
            elif mode == "top":
                target = min(r.top() for r in rects)
                deltas = [target - r.top() for r in rects]
                vectors = [QPointF(0.0, delta) for delta in deltas]
            elif mode == "bottom":
                target = max(r.bottom() for r in rects)
                deltas = [target - r.bottom() for r in rects]
                vectors = [QPointF(0.0, delta) for delta in deltas]
            else:  # middle
                target = sum(r.center().y() for r in rects) / len(rects)
                deltas = [target - r.center().y() for r in rects]
                vectors = [QPointF(0.0, delta) for delta in deltas]

            for item, vector in zip(items, vectors):
                new_pos = self.scene.snap_point(item.pos() + vector)
                item.setPos(new_pos)
                item.notify_geometry_changed()

        apply_alignment()
        after = [self.scene.capture_item_state(item) for item in items]
        self.scene.push_multi_state(items, before, after, f"Alinhar {mode}")
        self.scene.clear_alignment_guides()

    def _distribute_selected(self, orientation: str) -> None:
        items = self.scene.selected_label_items()
        if len(items) < 3:
            return
        rects = [item.mapToScene(item.boundingRect()).boundingRect() for item in items]
        combined = list(zip(items, rects))
        before = [self.scene.capture_item_state(item) for item in items]

        if orientation == "horizontal":
            combined.sort(key=lambda pair: pair[1].left())
            first_rect = combined[0][1]
            last_rect = combined[-1][1]
            span = last_rect.right() - first_rect.left()
            total_width = sum(rect.width() for _, rect in combined)
            gap = (span - total_width) / (len(combined) - 1) if span > total_width else 0.0
            position = first_rect.left() + first_rect.width() + gap
            for item, rect in combined[1:-1]:
                delta = position - rect.left()
                new_pos = self.scene.snap_point(item.pos() + QPointF(delta, 0.0))
                item.setPos(new_pos)
                item.notify_geometry_changed()
                position += rect.width() + gap
        else:
            combined.sort(key=lambda pair: pair[1].top())
            first_rect = combined[0][1]
            last_rect = combined[-1][1]
            span = last_rect.bottom() - first_rect.top()
            total_height = sum(rect.height() for _, rect in combined)
            gap = (span - total_height) / (len(combined) - 1) if span > total_height else 0.0
            position = first_rect.top() + first_rect.height() + gap
            for item, rect in combined[1:-1]:
                delta = position - rect.top()
                new_pos = self.scene.snap_point(item.pos() + QPointF(0.0, delta))
                item.setPos(new_pos)
                item.notify_geometry_changed()
                position += rect.height() + gap

        after = [self.scene.capture_item_state(item) for item in items]
        descricao = "Distribuir horizontalmente" if orientation == "horizontal" else "Distribuir verticalmente"
        self.scene.push_multi_state(items, before, after, descricao)
        self.scene.clear_alignment_guides()

    def _toggle_grid(self) -> None:
        state = self.grid_action.isChecked()
        self.scene.set_grid_visible(state)
        self.config["editor_grid_visible"] = state
        salvar_config(self.config)

    def _toggle_snap(self) -> None:
        state = self.snap_action.isChecked()
        self.scene.set_snap_to_grid(state)
        self.config["editor_snap"] = state
        salvar_config(self.config)

    def _zoom_in(self) -> None:
        self.view.zoom(1.2)
        self._update_zoom_label()

    def _zoom_out(self) -> None:
        self.view.zoom(0.8)
        self._update_zoom_label()

    def _zoom_reset(self) -> None:
        self.view.zoom_reset()
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        factor = self.view.transform().m11()
        self._zoom_label.setText(f"{int(factor * 100)}%")

    def _status_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    def _verificar_impressora(self) -> None:
        try:
            printers = listar_impressoras()
        except Exception as exc:  # pragma: no cover - consulta externa
            logger.warning("Falha ao listar impressoras", exc_info=exc)
            self.statusBar().showMessage("Erro ao consultar impressoras", 5000)
            return
        if printers:
            resumo = printers[0]
            if len(printers) > 1:
                resumo += f" (+{len(printers) - 1})"
            self.statusBar().showMessage(f"Impressoras disponíveis: {resumo}", 5000)
        else:
            self.statusBar().showMessage("Nenhuma impressora detectada", 5000)

    def _abrir_config(self) -> None:
        dialog = ConfigDialog(self, dict(self.config))
        exec_method = getattr(dialog, "exec", getattr(dialog, "exec_"))
        if exec_method() == QDialog.Accepted:
            updated = dialog.result_settings()
            self.config.update(updated)
            salvar_config(self.config)
            template = updated.get("template_editor")
            if template:
                index = self.template_combo.findText(str(template))
                if index >= 0 and self.template_combo.currentIndex() != index:
                    self.template_combo.setCurrentIndex(index)
                else:
                    self._load_template(str(template))
            self._verificar_impressora()

    def _mostrar_sobre(self) -> None:
        texto = (
            f"Gerador de Etiquetas — v{__version__}\n"
            f"Log: {LOG_FILE}\n"
            "Editor com suporte a desfazer, alinhamentos e visualização em tempo real."
        )
        QMessageBox.about(self, "Sobre", texto)

    def closeEvent(self, event) -> None:  # noqa: D401 - Qt API
        backup_automatico()
        if self._printer_refresh_timer is not None:
            self._printer_refresh_timer.stop()
        super().closeEvent(event)
