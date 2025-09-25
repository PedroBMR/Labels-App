"""High level widgets composing the label editor."""

from __future__ import annotations

import json
import math
from typing import Any, Mapping

from PIL.ImageQt import ImageQt

from qt_compat import (
    QColor,
    QGridLayout,
    QLabel,
    QPainter,
    QPixmap,
    QPointF,
    QSplitter,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from render.preview import render_template

from .items import GraphicsElementItem, TextGraphicsItem
from .properties import PropertyPanel
from .scene import LabelScene, build_model_from_scene
from .view import LabelView


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.label = QLabel("Pré-visualização")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: #fff; border: 1px solid #ccc;")
        layout.addWidget(self.label, 1)

    def set_image(self, image) -> None:
        if image is None:
            self.label.clear()
            self.label.setText("Pré-visualização")
            return
        pixmap = QPixmap.fromImage(ImageQt(image))
        self.label.setPixmap(pixmap)


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
        self.preview_widget = PreviewWidget()

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

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.addWidget(canvas_container)
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
        self.preview_widget.set_image(image)

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
