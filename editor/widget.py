"""High level widgets composing the label editor."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Mapping

from PIL.ImageQt import ImageQt

from qt_compat import (
    QBrush,
    QCheckBox,
    QColor,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPointF,
    QPixmap,
    QSlider,
    QSplitter,
    QStackedWidget,
    Qt,
    QTimer,
    QToolButton,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from render.preview import render_template

from .items import GraphicsElementItem, TextGraphicsItem
from .layers import LayerPanel
from .properties import PropertyPanel
from .scene import LabelScene, build_model_from_scene
from .view import LabelView


MM_PER_INCH = 25.4


class RulerWidget(QWidget):
    """Simple millimetre ruler aligned to the scene."""

    _MAJOR_TICK_INTERVAL = 10
    _MEDIUM_TICK_INTERVAL = 5

    def __init__(
        self,
        orientation: Qt.Orientation,
        scene: LabelScene,
        view: LabelView,
    ) -> None:
        super().__init__()
        self.orientation = orientation
        self.scene = scene
        self.view = view
        self.background = QColor(245, 245, 245)
        self.pen = QColor(120, 120, 120)
        if orientation == Qt.Horizontal:
            self.setFixedHeight(24)
        else:
            self.setFixedWidth(24)
        self.view.viewportChanged.connect(self.update)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: D401 - Qt API
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.background)
        painter.setPen(self.pen)

        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        if self.orientation == Qt.Horizontal:
            self._draw_horizontal_ticks(painter, visible)
        else:
            self._draw_vertical_ticks(painter, visible)

    # ------------------------------------------------------------------
    def _iter_visible_mm(self, start: float, end: float) -> range:
        start_mm = math.floor(start)
        end_mm = math.ceil(end)
        return range(start_mm, end_mm + 1)

    def _draw_horizontal_ticks(self, painter: QPainter, visible) -> None:
        to_scene_x = self.scene.mm_to_pixels_x
        to_view = self.view.mapFromScene
        height = self.height()
        for mm in self._iter_visible_mm(
            self.scene.to_mm_x(visible.left()), self.scene.to_mm_x(visible.right())
        ):
            scene_point = QPointF(to_scene_x(mm), visible.top())
            x = to_view(scene_point).x()
            self._draw_tick(painter, mm, int(x), height, orientation=Qt.Horizontal)

    def _draw_vertical_ticks(self, painter: QPainter, visible) -> None:
        to_scene_y = self.scene.mm_to_pixels_y
        to_view = self.view.mapFromScene
        width = self.width()
        for mm in self._iter_visible_mm(
            self.scene.to_mm_y(visible.top()), self.scene.to_mm_y(visible.bottom())
        ):
            scene_point = QPointF(visible.left(), to_scene_y(mm))
            y = to_view(scene_point).y()
            self._draw_tick(painter, mm, int(y), width, orientation=Qt.Vertical)

    def _draw_tick(
        self,
        painter: QPainter,
        mm: int,
        position: int,
        length: int,
        *,
        orientation: Qt.Orientation,
    ) -> None:
        if mm % self._MAJOR_TICK_INTERVAL == 0:
            self._draw_major_tick(painter, mm, position, length, orientation)
        elif mm % self._MEDIUM_TICK_INTERVAL == 0:
            self._draw_medium_tick(painter, position, length, orientation)
        else:
            self._draw_minor_tick(painter, position, length, orientation)

    def _draw_major_tick(
        self,
        painter: QPainter,
        mm: int,
        position: int,
        length: int,
        orientation: Qt.Orientation,
    ) -> None:
        if orientation == Qt.Horizontal:
            painter.drawLine(position, length, position, 0)
            painter.drawText(position + 2, length - 2, f"{mm}")
        else:
            painter.drawLine(length, position, 0, position)
            painter.save()
            painter.translate(2, position - 2)
            painter.rotate(-90)
            painter.drawText(0, 0, f"{mm}")
            painter.restore()

    def _draw_medium_tick(
        self,
        painter: QPainter,
        position: int,
        length: int,
        orientation: Qt.Orientation,
    ) -> None:
        if orientation == Qt.Horizontal:
            painter.drawLine(position, length, position, length // 2)
        else:
            painter.drawLine(length, position, length // 2, position)

    def _draw_minor_tick(
        self,
        painter: QPainter,
        position: int,
        length: int,
        orientation: Qt.Orientation,
    ) -> None:
        if orientation == Qt.Horizontal:
            painter.drawLine(position, length, position, length - 6)
        else:
            painter.drawLine(length, position, length - 6, position)


class PreviewWidget(QWidget):
    """Widget showing the Pillow generated preview."""

    refresh_requested = pyqtSignal()

    _MIN_ZOOM = 10
    _MAX_ZOOM = 400

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._pixmap: QPixmap | None = None
        self._fit_to_screen = False
        self._last_updated: datetime | None = None
        self._checkerboard_brush = self._build_checkerboard_brush()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(4)

        self.zoom_out_button = QToolButton(self)
        self.zoom_out_button.setText("-")
        self.zoom_out_button.setToolTip("Reduzir zoom")
        self.zoom_out_button.clicked.connect(self._zoom_out)
        controls.addWidget(self.zoom_out_button)

        self.zoom_slider = QSlider(Qt.Horizontal, self)
        self.zoom_slider.setRange(self._MIN_ZOOM, self._MAX_ZOOM)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        controls.addWidget(self.zoom_slider, 1)

        self.zoom_in_button = QToolButton(self)
        self.zoom_in_button.setText("+")
        self.zoom_in_button.setToolTip("Aumentar zoom")
        self.zoom_in_button.clicked.connect(self._zoom_in)
        controls.addWidget(self.zoom_in_button)

        self.zoom_label = QLabel("100%", self)
        controls.addWidget(self.zoom_label)

        self.fit_button = QToolButton(self)
        self.fit_button.setText("Ajustar")
        self.fit_button.setToolTip("Ajustar à tela")
        self.fit_button.clicked.connect(self._fit_view)
        controls.addWidget(self.fit_button)

        self.reset_button = QToolButton(self)
        self.reset_button.setText("Reset")
        self.reset_button.setToolTip("Restaurar visualização")
        self.reset_button.clicked.connect(self._reset_view)
        controls.addWidget(self.reset_button)

        self.refresh_button = QToolButton(self)
        self.refresh_button.setText("Atualizar")
        self.refresh_button.setToolTip("Recarregar pré-visualização")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        controls.addWidget(self.refresh_button)

        self.checkerboard_toggle = QCheckBox("Fundo xadrez", self)
        self.checkerboard_toggle.toggled.connect(self._update_background)
        controls.addWidget(self.checkerboard_toggle)

        layout.addLayout(controls)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(self.view.renderHints() | QPainter.Antialiasing)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setBackgroundBrush(QColor("#ffffff"))

        self.placeholder = QLabel("Pré-visualização", self)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("background: #fff; border: 1px solid #ccc;")

        self.stacked = QStackedWidget(self)
        self.stacked.addWidget(self.placeholder)
        self.stacked.addWidget(self.view)
        self.stacked.setCurrentWidget(self.placeholder)

        layout.addWidget(self.stacked, 1)

        self.metadata_label = QLabel("Sem dados de pré-visualização", self)
        self.metadata_label.setAlignment(Qt.AlignLeft)
        self.metadata_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.metadata_label)

        self._update_controls_enabled(False)

    # ------------------------------------------------------------------
    def _build_checkerboard_brush(self) -> QBrush:
        size = 12
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(QColor(220, 220, 220))
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, size, size, QColor(245, 245, 245))
        painter.fillRect(size, size, size, size, QColor(245, 245, 245))
        painter.end()
        return QBrush(pixmap)

    def _update_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.zoom_out_button,
            self.zoom_in_button,
            self.zoom_slider,
            self.fit_button,
            self.reset_button,
            self.checkerboard_toggle,
        ):
            widget.setEnabled(enabled)

    def _update_background(self, checked: bool) -> None:
        if checked:
            self.view.setBackgroundBrush(self._checkerboard_brush)
        else:
            self.view.setBackgroundBrush(QColor("#ffffff"))

    def _update_zoom_label(self, value: int | None = None) -> None:
        percent = value if value is not None else self.zoom_slider.value()
        self.zoom_label.setText(f"{percent}%")

    def _zoom_in(self) -> None:
        if self._pixmap is None:
            return
        self._fit_to_screen = False
        self.zoom_slider.setValue(min(self.zoom_slider.value() + 10, self._MAX_ZOOM))

    def _zoom_out(self) -> None:
        if self._pixmap is None:
            return
        self._fit_to_screen = False
        self.zoom_slider.setValue(max(self.zoom_slider.value() - 10, self._MIN_ZOOM))

    def _reset_view(self) -> None:
        if self._pixmap is None:
            return
        self._fit_to_screen = False
        self.zoom_slider.setValue(100)
        self.checkerboard_toggle.setChecked(False)
        self._apply_zoom()

    def _fit_view(self) -> None:
        if self._pixmap_item is None:
            return
        self._fit_to_screen = True
        self.view.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        transform = self.view.transform()
        scale_percent = max(
            self._MIN_ZOOM,
            min(int(round(transform.m11() * 100)), self._MAX_ZOOM),
        )
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(scale_percent)
        self.zoom_slider.blockSignals(False)
        self._update_zoom_label(scale_percent)

    def _apply_zoom(self) -> None:
        if self._pixmap is None:
            return
        self.view.resetTransform()
        scale = self.zoom_slider.value() / 100.0
        self.view.scale(scale, scale)
        self._update_zoom_label()

    def _on_zoom_slider_changed(self, value: int) -> None:
        if self._pixmap is None:
            return
        self._fit_to_screen = False
        self._apply_zoom()

    # ------------------------------------------------------------------
    def set_image(self, image, metadata: Mapping[str, Any] | None = None) -> None:
        if image is None:
            self._pixmap = None
            self._pixmap_item = None
            self.scene.clear()
            self.stacked.setCurrentWidget(self.placeholder)
            self.placeholder.setText("Pré-visualização")
            self.metadata_label.setText("Sem dados de pré-visualização")
            self._update_controls_enabled(False)
            return

        qimage = ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap = pixmap

        self.scene.clear()
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(pixmap.rect())
        self.stacked.setCurrentWidget(self.view)
        self._update_controls_enabled(True)

        if self._fit_to_screen:
            self._fit_view()
        else:
            self._apply_zoom()

        self._last_updated = datetime.now()
        self._update_metadata(metadata)

    def _update_metadata(self, metadata: Mapping[str, Any] | None) -> None:
        if self._pixmap is None:
            self.metadata_label.setText("Sem dados de pré-visualização")
            return

        def to_float(value: Any) -> float | None:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        width_mm = to_float(metadata.get("width_mm")) if metadata else None
        height_mm = to_float(metadata.get("height_mm")) if metadata else None
        dpi = to_float(metadata.get("dpi")) if metadata else None
        width_px = self._pixmap.width()
        height_px = self._pixmap.height()

        parts: list[str] = []
        if width_mm is not None and height_mm is not None:
            parts.append(f"{width_mm:.1f} mm × {height_mm:.1f} mm")
        parts.append(f"{width_px} × {height_px} px")
        if dpi is not None:
            parts.append(f"{dpi:.0f} DPI")
        if self._last_updated:
            parts.append(self._last_updated.strftime("Atualizado em %d/%m/%Y %H:%M:%S"))

        self.metadata_label.setText(" | ".join(parts))


class LabelEditorWidget(QWidget):
    """Composite widget exposing canvas, properties and preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = LabelScene()
        self.view = LabelView()
        self.view.setScene(self.scene)
        self.preview_variables: dict[str, Any] = {}
        self._last_preview_payload: tuple[str, str] | None = None
        self._preview_delay_ms = 75
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._perform_preview_update)

        self.property_panel = PropertyPanel()
        self.property_panel.set_scene(self.scene)
        self.layer_panel = LayerPanel()
        self.layer_panel.set_scene(self.scene)
        self.layer_panel.alignmentToleranceChanged.connect(
            self._on_alignment_tolerance_changed
        )
        self.preview_widget = PreviewWidget()
        self.preview_widget.refresh_requested.connect(
            lambda: self.update_preview(immediate=True)
        )

        self.h_ruler = RulerWidget(Qt.Horizontal, self.scene, self.view)
        self.v_ruler = RulerWidget(Qt.Vertical, self.scene, self.view)

        canvas_layout = QGridLayout()
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(QWidget(), 0, 0)
        canvas_layout.addWidget(self.h_ruler, 0, 1)
        canvas_layout.addWidget(self.v_ruler, 1, 0)
        canvas_layout.addWidget(self.view, 1, 1)
        canvas_container = QWidget()
        canvas_container.setLayout(canvas_layout)

        self.canvas_splitter = QSplitter()
        self.canvas_splitter.setOrientation(Qt.Horizontal)
        self.canvas_splitter.addWidget(self.layer_panel)
        self.canvas_splitter.addWidget(canvas_container)
        self.canvas_splitter.setStretchFactor(0, 0)
        self.canvas_splitter.setStretchFactor(1, 1)
        self.canvas_splitter.setCollapsible(0, False)

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.addWidget(self.canvas_splitter)
        self.splitter.addWidget(self.preview_widget)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.splitter, 0, 0)

        self.scene.undo_stack.indexChanged.connect(self.update_preview)
        self.scene.selectionChanged.connect(self.update_preview)
        self.view.viewportChanged.connect(self._update_rulers)
        self.update_preview(immediate=True)

    # ------------------------------------------------------------------
    def alignment_tolerance(self) -> float:
        return self.scene.alignment_tolerance()

    def set_alignment_tolerance(self, tolerance: float) -> None:
        self.scene.set_alignment_tolerance(tolerance)
        self.layer_panel.set_alignment_tolerance(self.scene.alignment_tolerance())

    def _on_alignment_tolerance_changed(self, tolerance: float) -> None:
        self.set_alignment_tolerance(tolerance)

    # ------------------------------------------------------------------
    def _update_rulers(self) -> None:
        self.h_ruler.update()
        self.v_ruler.update()

    def add_element(
        self, element: Mapping[str, Any]
    ) -> GraphicsElementItem | TextGraphicsItem:
        item = self.scene.add_element(element)
        item.changed.connect(self.update_preview)
        self.scene.clearSelection()
        item.setSelected(True)
        self.view.ensureVisible(item, 50, 50)
        self.update_preview(immediate=True)
        return item

    def load_document(self, document) -> None:
        self.scene.load_document(document)
        for item in self.scene.editable_items():
            item.changed.connect(self.update_preview)
        self.scene.clearSelection()
        self._last_preview_payload = None
        self.update_preview(immediate=True)

    def to_document(self, name: str, variables: Mapping[str, Any] | None = None):
        return self.scene.to_template(name, variables)

    def set_preview_data(self, data: Mapping[str, Any]) -> None:
        self.preview_variables = dict(data)
        self.scene.set_preview_variables(data)
        self._last_preview_payload = None
        self.update_preview()

    def update_preview(self, *_, immediate: bool = False) -> None:
        if immediate:
            self._preview_timer.stop()
            self._perform_preview_update()
            return
        self._preview_timer.start(self._preview_delay_ms)

    def _perform_preview_update(self) -> None:
        model = build_model_from_scene(
            self.scene,
            str(self.scene.page.get("name", "Preview")),
        )
        backend_dict = model.as_backend_dict()
        context = dict(self.preview_variables)
        payload_signature = (
            json.dumps(backend_dict, sort_keys=True, ensure_ascii=False),
            json.dumps(context, sort_keys=True, ensure_ascii=False),
        )
        if payload_signature == self._last_preview_payload:
            return

        image = render_template(
            backend_dict,
            context,
            calibration=self.scene.calibration,
        )
        self._last_preview_payload = payload_signature
        metadata = self._build_preview_metadata(backend_dict.get("page", {}))
        self.preview_widget.set_image(image, metadata)

    def _build_preview_metadata(self, page: Mapping[str, Any]) -> Mapping[str, Any]:
        def to_float(value: Any) -> float | None:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        width_mm = to_float(page.get("width_mm")) or to_float(page.get("width"))
        height_mm = to_float(page.get("height_mm")) or to_float(page.get("height"))
        dpi = to_float(page.get("dpi"))
        if dpi is None:
            dots_per_mm = to_float(page.get("dots_per_mm"))
            if dots_per_mm:
                dpi = dots_per_mm * MM_PER_INCH
        metadata: dict[str, Any] = {}
        if width_mm is not None:
            metadata["width_mm"] = width_mm
        if height_mm is not None:
            metadata["height_mm"] = height_mm
        if dpi is not None:
            metadata["dpi"] = dpi
        return metadata

    def create_default(self, kind: str) -> dict[str, Any]:
        if kind == "text":
            page_width = float(self.scene.page.get("width_mm", 80.0) or 80.0)
            page_height = float(self.scene.page.get("height_mm", 60.0) or 60.0)
            width = 30.0
            height = 10.0
            return {
                "type": "text",
                "x_mm": max(0.0, (page_width - width) / 2),
                "y_mm": max(0.0, (page_height - height) / 2),
                "width_mm": width,
                "height_mm": height,
                "content": "New Text",
                "font": {"size": 22},
            }
        if kind == "barcode":
            return {
                "type": "barcode",
                "x_mm": 5,
                "y_mm": 20,
                "width_mm": 50,
                "height_mm": 20,
                "value": "123456789012",
                "symbology": "code128",
            }
        if kind == "qr":
            return {
                "type": "qr",
                "x_mm": 10,
                "y_mm": 10,
                "width_mm": 25,
                "height_mm": 25,
                "value": "https://",
                "error": "M",
            }
        if kind == "image":
            return {
                "type": "image",
                "x_mm": 10,
                "y_mm": 10,
                "width_mm": 30,
                "height_mm": 20,
                "fit": "contain",
            }
        if kind == "shape":
            return {
                "type": "shape",
                "kind": "rect",
                "x_mm": 2,
                "y_mm": 2,
                "width_mm": 40,
                "height_mm": 30,
                "thickness_mm": 0.5,
            }
        raise ValueError(f"Tipo desconhecido: {kind}")
