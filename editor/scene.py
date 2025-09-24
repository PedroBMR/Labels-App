"""Graphics scene implementing the WYSIWYG label editor."""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from compile import Calibration, SafeDict
from model.template import TemplateDocument
from qt_compat import (
    QColor,
    QGraphicsLineItem,
    QGraphicsScene,
    QPainter,
    QPen,
    QPointF,
    QRectF,
    Qt,
    QUndoCommand,
    QUndoStack,
)

from .items import GraphicsElementItem, create_item, iter_element_items


def _compute_dots_per_mm(page: Mapping[str, Any]) -> float:
    if "dots_per_mm" in page:
        try:
            return float(page["dots_per_mm"])
        except (TypeError, ValueError):  # pragma: no cover - defensive
            pass
    dpi = page.get("dpi", 203)
    try:
        return float(dpi) / 25.4
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 203 / 25.4


class _StateChange(QUndoCommand):
    item: GraphicsElementItem
    before: Any
    after: Any

    def __init__(
        self,
        item: GraphicsElementItem,
        before: Any,
        after: Any,
        text: str,
    ) -> None:
        super().__init__(text)
        self.item = item
        self.before = before
        self.after = after

    def undo(self) -> None:  # noqa: D401 - Qt API
        self.item.restore_state(self.before)

    def redo(self) -> None:  # noqa: D401 - Qt API
        self.item.restore_state(self.after)


class LabelScene(QGraphicsScene):
    """Scene containing all editable items for a template."""

    def __init__(
        self,
        page: Mapping[str, Any] | None = None,
        *,
        grid_mm: float = 1.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page: dict[str, Any] = dict(
            page or {"width_mm": 80.0, "height_mm": 60.0, "dpi": 203}
        )
        self.grid_mm = max(0.1, float(grid_mm))
        self.calibration = Calibration()
        self.undo_stack = QUndoStack(self)
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._variables: dict[str, Any] = {}
        self._guides: list[QGraphicsLineItem] = []
        self._grid_pen = QPen(QColor(220, 220, 220))
        self._grid_pen.setWidth(0)
        self._guide_pen = QPen(QColor(255, 128, 0))
        self._guide_pen.setWidth(0)
        self._alignment_tolerance = 6.0
        self.setBackgroundBrush(QColor(250, 250, 250))
        self._update_scene_rect()

    # ------------------------------------------------------------------
    def set_page(self, page: Mapping[str, Any]) -> None:
        self.page = dict(page)
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._update_scene_rect()
        for item in iter_element_items(self.items()):
            item.apply_element(item.to_dict())

    def _update_scene_rect(self) -> None:
        width = self.page.get("width_mm", 80.0)
        height = self.page.get("height_mm", 60.0)
        rect = QRectF(0, 0, self.mm_to_pixels_x(width), self.mm_to_pixels_y(height))
        self.setSceneRect(rect)

    # ------------------------------------------------------------------
    def mm_to_pixels_x(self, value: float) -> float:
        return value * self._dots_per_mm * self.calibration.scale_x

    def mm_to_pixels_y(self, value: float) -> float:
        return value * self._dots_per_mm * self.calibration.scale_y

    def to_mm_x(self, value: float) -> float:
        base = self._dots_per_mm * self.calibration.scale_x
        return value / base if base else value

    def to_mm_y(self, value: float) -> float:
        base = self._dots_per_mm * self.calibration.scale_y
        return value / base if base else value

    def grid_pixels(self) -> float:
        return self.mm_to_pixels_x(self.grid_mm)

    # ------------------------------------------------------------------
    def preview_context(self) -> SafeDict:
        return SafeDict(dict(self._variables))

    def set_preview_variables(self, variables: Mapping[str, Any]) -> None:
        self._variables = dict(variables)
        for item in iter_element_items(self.items()):
            item.apply_element(item.to_dict())

    # ------------------------------------------------------------------
    def add_element(self, element: Mapping[str, Any]) -> GraphicsElementItem:
        item = create_item(element)
        self.addItem(item)
        item.geometryCommitted.connect(self._on_geometry_committed)
        return item

    def delete_item(self, item: GraphicsElementItem) -> None:
        self.removeItem(item)

    def element_rect(self, element: Mapping[str, Any]) -> QRectF:
        width = float(element.get("width_mm", 20.0))
        height = float(element.get("height_mm", 10.0))
        x = float(element.get("x_mm", 0.0))
        y = float(element.get("y_mm", 0.0))
        rect = QRectF(
            self.mm_to_pixels_x(x),
            self.mm_to_pixels_y(y),
            max(1.0, self.mm_to_pixels_x(width)),
            max(1.0, self.mm_to_pixels_y(height)),
        )
        return rect

    # ------------------------------------------------------------------
    def snap_point(self, item: GraphicsElementItem, new_pos: QPointF) -> QPointF:
        grid = self.grid_pixels()
        if grid > 0.0:
            new_pos.setX(round(new_pos.x() / grid) * grid)
            new_pos.setY(round(new_pos.y() / grid) * grid)
        rect = item.shapeRect()
        rect.moveTo(new_pos)
        aligned = self._align_rect(item, rect)
        return aligned.topLeft()

    def snap_rect(self, rect: QRectF, item: GraphicsElementItem) -> QRectF:
        grid = self.grid_pixels()
        snapped = QRectF(rect)
        if grid > 0.0:
            left = round(snapped.left() / grid) * grid
            top = round(snapped.top() / grid) * grid
            right = round(snapped.right() / grid) * grid
            bottom = round(snapped.bottom() / grid) * grid
            snapped = QRectF(
                left,
                top,
                max(grid, right - left),
                max(grid, bottom - top),
            )
        return self._align_rect(item, snapped)

    def snap_rotation(self, angle: float) -> float:
        return round(angle / 5.0) * 5.0

    def clear_guides(self) -> None:
        for guide in self._guides:
            self.removeItem(guide)
        self._guides.clear()

    # ------------------------------------------------------------------
    def _align_rect(self, item: GraphicsElementItem, rect: QRectF) -> QRectF:
        tolerance = self._alignment_tolerance
        best_rect = QRectF(rect)
        best_diff_x = tolerance
        best_diff_y = tolerance
        vertical_guides: list[float] = []
        horizontal_guides: list[float] = []

        for other in iter_element_items(self.items()):
            if other is item or not other.isVisible():
                continue
            other_rect = other.sceneBoundingRect()

            rect_edges = [
                (rect.left(), "left"),
                (rect.center().x(), "center"),
                (rect.right(), "right"),
            ]
            other_edges = [
                (other_rect.left(), "left"),
                (other_rect.center().x(), "center"),
                (other_rect.right(), "right"),
            ]
            for value, name in rect_edges:
                for other_value, _ in other_edges:
                    diff = abs(value - other_value)
                    if diff < best_diff_x:
                        best_diff_x = diff
                        offset = other_value - value
                        best_rect.moveLeft(rect.left() + offset)
                        vertical_guides = [other_value]

            rect_edges_y = [
                (rect.top(), "top"),
                (rect.center().y(), "center"),
                (rect.bottom(), "bottom"),
            ]
            other_edges_y = [
                (other_rect.top(), "top"),
                (other_rect.center().y(), "center"),
                (other_rect.bottom(), "bottom"),
            ]
            for value, name in rect_edges_y:
                for other_value, _ in other_edges_y:
                    diff = abs(value - other_value)
                    if diff < best_diff_y:
                        best_diff_y = diff
                        offset = other_value - value
                        best_rect.moveTop(rect.top() + offset)
                        horizontal_guides = [other_value]

        self.clear_guides()
        if vertical_guides:
            for x in vertical_guides:
                guide = self.addLine(
                    x,
                    0,
                    x,
                    self.sceneRect().height(),
                    self._guide_pen,
                )
                guide.setZValue(9999)
                self._guides.append(guide)
        if horizontal_guides:
            for y in horizontal_guides:
                guide = self.addLine(
                    0,
                    y,
                    self.sceneRect().width(),
                    y,
                    self._guide_pen,
                )
                guide.setZValue(9999)
                self._guides.append(guide)
        return best_rect

    # ------------------------------------------------------------------
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: D401 - Qt API
        super().drawBackground(painter, rect)

        label_rect = self.sceneRect()
        if label_rect.isNull():
            return

        painter.save()
        shadow = label_rect.adjusted(3, 3, 6, 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawRoundedRect(shadow, 6, 6)
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRoundedRect(label_rect, 6, 6)
        painter.restore()

        grid = self.grid_pixels()
        if grid <= 0:
            return

        target = rect.intersected(label_rect)
        if target.isNull():
            return

        painter.save()
        painter.setClipRect(label_rect)
        painter.setPen(self._grid_pen)
        left = math.floor(target.left() / grid) * grid
        top = math.floor(target.top() / grid) * grid
        x = left
        while x <= target.right():
            painter.drawLine(x, target.top(), x, target.bottom())
            x += grid
        y = top
        while y <= target.bottom():
            painter.drawLine(target.left(), y, target.right(), y)
            y += grid
        painter.restore()

    # ------------------------------------------------------------------
    def _on_geometry_committed(self, item: GraphicsElementItem, before, after) -> None:
        command = _StateChange(item, before, after, "Mover elemento")
        self.undo_stack.push(command)

    def change_property(self, item: GraphicsElementItem, name: str, value: Any) -> None:
        current = copy.deepcopy(item.element.get(name))
        if name == "font":
            current = copy.deepcopy(item.element.get("font", {}))
        if current == value:
            return
        command = _PropertyChange(item, name, current, value)
        self.undo_stack.push(command)

    # ------------------------------------------------------------------
    def to_template(
        self,
        name: str,
        variables: Mapping[str, Any] | None = None,
    ) -> TemplateDocument:
        elements = [
            item.to_dict() for item in iter_element_items(self.items())
        ]
        page = dict(self.page)
        document = TemplateDocument(
            name=name,
            page=page,
            elements=elements,
            variables=dict(variables or {}),
        )
        return document

    def load_document(self, document: TemplateDocument) -> None:
        self.clear()
        self.page = document.page
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._update_scene_rect()
        for element in document.elements:
            self.add_element(element)

    # ------------------------------------------------------------------
    def selected_items(self) -> list[GraphicsElementItem]:
        return list(iter_element_items(self.selectedItems()))

    def bring_to_front(self) -> None:
        for index, item in enumerate(self.selected_items(), start=1):
            item.setZValue(item.zValue() + 10 * index)

    def send_to_back(self) -> None:
        for index, item in enumerate(self.selected_items(), start=1):
            item.setZValue(item.zValue() - 10 * index)

    def align_left(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        min_left = min(item.pos().x() for item in selected)
        for item in selected:
            item.setX(min_left)

    def align_right(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        max_right = max(item.pos().x() + item.shapeRect().width() for item in selected)
        for item in selected:
            item.setX(max_right - item.shapeRect().width())

    def align_top(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        min_top = min(item.pos().y() for item in selected)
        for item in selected:
            item.setY(min_top)

    def align_bottom(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        max_bottom = max(
            item.pos().y() + item.shapeRect().height() for item in selected
        )
        for item in selected:
            item.setY(max_bottom - item.shapeRect().height())

    def distribute_horizontally(self) -> None:
        selected = sorted(self.selected_items(), key=lambda item: item.pos().x())
        if len(selected) < 3:
            return
        left = selected[0].pos().x()
        right = selected[-1].pos().x()
        total_width = sum(item.shapeRect().width() for item in selected)
        spacing = (right - left - total_width) / (len(selected) - 1)
        cursor = left
        for item in selected:
            item.setX(cursor)
            cursor += item.shapeRect().width() + spacing

    def distribute_vertically(self) -> None:
        selected = sorted(self.selected_items(), key=lambda item: item.pos().y())
        if len(selected) < 3:
            return
        top = selected[0].pos().y()
        bottom = selected[-1].pos().y()
        total_height = sum(item.shapeRect().height() for item in selected)
        spacing = (bottom - top - total_height) / (len(selected) - 1)
        cursor = top
        for item in selected:
            item.setY(cursor)
            cursor += item.shapeRect().height() + spacing


class _PropertyChange(QUndoCommand):
    def __init__(
        self,
        item: GraphicsElementItem,
        name: str,
        before: Any,
        after: Any,
    ) -> None:
        super().__init__(f"Alterar {name}")
        self.item = item
        self.name = name
        self.before = copy.deepcopy(before)
        self.after = copy.deepcopy(after)

    def undo(self) -> None:  # noqa: D401 - Qt API
        self.item.update_property(self.name, copy.deepcopy(self.before))

    def redo(self) -> None:  # noqa: D401 - Qt API
        self.item.update_property(self.name, copy.deepcopy(self.after))

