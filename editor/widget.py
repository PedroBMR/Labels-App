"""High level widgets composing the label editor."""

from __future__ import annotations

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
    QVBoxLayout,
    QWidget,
)
from render.preview import render_template

from .items import GraphicsElementItem, iter_element_items
from .properties import PropertyPanel
from .scene import LabelScene
from .view import LabelView


class RulerWidget(QWidget):
    """Simple millimetre ruler aligned to the scene."""

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

    def paintEvent(self, event) -> None:  # noqa: D401 - Qt API
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.background)
        painter.setPen(self.pen)

        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        if self.orientation == Qt.Horizontal:
            start_mm = math.floor(self.scene.to_mm_x(visible.left()))
            end_mm = math.ceil(self.scene.to_mm_x(visible.right()))
            for mm in range(start_mm, end_mm + 1):
                scene_point = QPointF(self.scene.mm_to_pixels_x(mm), visible.top())
                view_point = self.view.mapFromScene(scene_point)
                x = view_point.x()
                if mm % 10 == 0:
                    painter.drawLine(int(x), self.height(), int(x), 0)
                    painter.drawText(int(x) + 2, self.height() - 2, f"{mm}")
                elif mm % 5 == 0:
                    painter.drawLine(int(x), self.height(), int(x), self.height() // 2)
                else:
                    painter.drawLine(int(x), self.height(), int(x), self.height() - 6)
        else:
            start_mm = math.floor(self.scene.to_mm_y(visible.top()))
            end_mm = math.ceil(self.scene.to_mm_y(visible.bottom()))
            for mm in range(start_mm, end_mm + 1):
                scene_point = QPointF(visible.left(), self.scene.mm_to_pixels_y(mm))
                view_point = self.view.mapFromScene(scene_point)
                y = view_point.y()
                if mm % 10 == 0:
                    painter.drawLine(self.width(), int(y), 0, int(y))
                    painter.save()
                    painter.translate(2, int(y) - 2)
                    painter.rotate(-90)
                    painter.drawText(0, 0, f"{mm}")
                    painter.restore()
                elif mm % 5 == 0:
                    painter.drawLine(self.width(), int(y), self.width() // 2, int(y))
                else:
                    painter.drawLine(self.width(), int(y), self.width() - 6, int(y))


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
        self.update_preview()

    # ------------------------------------------------------------------
    def _update_rulers(self) -> None:
        self.h_ruler.update()
        self.v_ruler.update()

    def add_element(self, element: Mapping[str, Any]) -> GraphicsElementItem:
        item = self.scene.add_element(element)
        item.changed.connect(self.update_preview)
        item.setSelected(True)
        self.update_preview()
        return item

    def load_document(self, document) -> None:
        self.scene.load_document(document)
        for item in iter_element_items(self.scene.items()):
            item.changed.connect(self.update_preview)
        self.update_preview()

    def to_document(self, name: str, variables: Mapping[str, Any] | None = None):
        return self.scene.to_template(name, variables)

    def set_preview_data(self, data: Mapping[str, Any]) -> None:
        self.preview_variables = dict(data)
        self.scene.set_preview_variables(data)
        self.update_preview()

    def update_preview(self) -> None:
        elements = [
            item.to_dict()
            for item in self.scene.items()
            if isinstance(item, GraphicsElementItem)
        ]
        template = {"page": self.scene.page, "elements": elements}
        context = dict(self.preview_variables)
        image = render_template(template, context, calibration=self.scene.calibration)
        self.preview_widget.set_image(image)

    def create_default(self, kind: str) -> dict[str, Any]:
        if kind == "text":
            return {
                "type": "text",
                "x_mm": 5,
                "y_mm": 5,
                "width_mm": 30,
                "height_mm": 10,
                "content": "Novo texto",
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
