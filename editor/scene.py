"""Graphics scene implementing the WYSIWYG label editor."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from compile import Calibration, SafeDict
from fonts import font_store
from model.template import TemplateDocument
from qt_compat import (
    QT_API,
    QColor,
    QGraphicsLineItem,
    QGraphicsScene,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPointF,
    QRectF,
    Qt,
    QUndoCommand,
    QUndoStack,
    pyqtSignal,
)

try:  # pragma: no cover - optional dependency per Qt binding
    from shiboken6 import shiboken6
except Exception:  # pragma: no cover - best-effort fallback
    shiboken6 = None

try:  # pragma: no cover - optional dependency per Qt binding
    import sip
except Exception:  # pragma: no cover - best-effort fallback
    sip = None

from .items import (
    GraphicsElementItem,
    TextGraphicsItem,
    create_base_rect_item,
    create_item,
    create_text_item,
)


def build_model_from_scene(
    scene: "LabelScene",
    name: str,
    variables: Mapping[str, Any] | None = None,
) -> TemplateDocument:
    """Return a :class:`TemplateDocument` representing ``scene``."""

    elements: list[dict[str, Any]] = []
    for item in scene.editable_items():
        if not item.isVisible():
            continue
        element = item.to_dict()
        if bool(element.get("hidden")):
            continue
        if str(element.get("type", "")).lower() == "text":
            element["font"] = scene._normalise_font_value(element.get("font"))
        elements.append(element)
    page = dict(scene.page)
    font_ids: set[str] = set()
    for element in elements:
        font_spec = element.get("font")
        if not isinstance(font_spec, Mapping):
            continue
        ttf_spec = font_spec.get("ttf")
        if isinstance(ttf_spec, Mapping):
            font_id = str(ttf_spec.get("id", ""))
            if font_id:
                font_ids.add(font_id)
    metadata = dict(scene.metadata)
    if font_ids:
        fonts_metadata = scene.export_fonts(font_ids)
        if fonts_metadata:
            metadata["fonts"] = fonts_metadata
        else:
            metadata.pop("fonts", None)
    else:
        metadata.pop("fonts", None)
    return TemplateDocument(
        name=name,
        page=page,
        elements=elements,
        variables=dict(variables or {}),
        metadata=metadata,
    )


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
    item: GraphicsElementItem | TextGraphicsItem
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


def _is_valid_graphics_item(item: QGraphicsLineItem | None) -> bool:
    """Return ``True`` when ``item`` still has a valid C++ backing object."""

    if item is None:
        return False
    if QT_API == "PySide6" and shiboken6 is not None:
        return shiboken6.isValid(item)
    if QT_API == "PyQt5" and sip is not None:
        return not sip.isdeleted(item)
    try:  # pragma: no cover - defensive fallback
        item.scene()
    except RuntimeError:
        return False
    return True


class LabelScene(QGraphicsScene):
    """Scene containing all editable items for a template."""

    itemsChanged = pyqtSignal()
    historyChanged = pyqtSignal()

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
        self._history_snapshots: list[QPixmap] = []
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._variables: dict[str, Any] = {}
        self._guides: list[QGraphicsLineItem] = []
        self._grid_pen = QPen(QColor(220, 220, 220))
        self._grid_pen.setWidth(0)
        self._guide_pen = QPen(QColor(255, 128, 0))
        self._guide_pen.setWidth(0)
        self._alignment_tolerance = 6.0
        self.setBackgroundBrush(QColor(250, 250, 250))
        self._base_rect = None
        self.metadata: dict[str, Any] = {}
        self._metadata_fonts: dict[str, Any] = {}
        self._default_name_map = {
            "text": "Texto",
            "barcode": "Código de barras",
            "qr": "QR Code",
            "qrcode": "QR Code",
            "image": "Imagem",
            "shape": "Forma",
        }
        self._update_scene_rect()
        self.reset_history_snapshots()

    # ------------------------------------------------------------------
    def set_page(self, page: Mapping[str, Any]) -> None:
        self.page = dict(page)
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._update_scene_rect()
        for item in self._iter_editable_items():
            item.apply_element(item.to_dict())

    def _update_scene_rect(self) -> None:
        width = self.page.get("width_mm", 80.0)
        height = self.page.get("height_mm", 60.0)
        rect = QRectF(0, 0, self.mm_to_pixels_x(width), self.mm_to_pixels_y(height))
        self.setSceneRect(rect)
        self._ensure_base_rect(rect)

    def _ensure_base_rect(self, rect: QRectF) -> None:
        if self._base_rect is None:
            self._base_rect = create_base_rect_item(rect)
            self._base_rect.setPen(QPen(QColor(210, 210, 210)))
            self._base_rect.setZValue(-100)
            self._base_rect.setAcceptedMouseButtons(Qt.NoButton)
            self.addItem(self._base_rect)
        else:
            self._base_rect.prepareGeometryChange()
            self._base_rect.setRect(rect)
            self._base_rect.setPos(0, 0)

    def reset_history_snapshots(self) -> None:
        """Reset stored history thumbnails to the current scene state."""

        snapshot = self.capture_thumbnail()
        self._history_snapshots = [snapshot]
        self.historyChanged.emit()

    def history_snapshots(self) -> list[QPixmap]:
        return list(self._history_snapshots)

    def _push_command(self, command: QUndoCommand) -> None:
        """Push ``command`` to the undo stack updating history thumbnails."""

        index = self.undo_stack.index()
        if index < len(self._history_snapshots) - 1:
            self._history_snapshots = self._history_snapshots[: index + 1]
        self.undo_stack.push(command)
        snapshot = self.capture_thumbnail()
        index = self.undo_stack.index()
        if index < len(self._history_snapshots):
            self._history_snapshots[index] = snapshot
        else:
            self._history_snapshots.append(snapshot)
        self.historyChanged.emit()

    def capture_thumbnail(self, size: int = 120, padding: int = 6) -> QPixmap:
        """Capture a thumbnail representation of the current scene state."""

        rect = self.sceneRect()
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(245, 245, 245))
        if rect.width() <= 0 or rect.height() <= 0:
            return QPixmap.fromImage(image)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        available = max(1.0, size - padding * 2)
        scale = min(available / rect.width(), available / rect.height())
        width = rect.width() * scale
        height = rect.height() * scale
        target = QRectF(
            (size - width) / 2,
            (size - height) / 2,
            width,
            height,
        )
        self.render(painter, target, rect)
        painter.end()
        return QPixmap.fromImage(image)

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
        for item in self._iter_editable_items():
            item.apply_element(item.to_dict())

    def _iter_editable_items(self):
        for item in self.items():
            if isinstance(item, (GraphicsElementItem, TextGraphicsItem)):
                yield item

    def editable_items(self) -> list[GraphicsElementItem | TextGraphicsItem]:
        return list(self._iter_editable_items())

    # ------------------------------------------------------------------
    def add_element(
        self, element: Mapping[str, Any]
    ) -> GraphicsElementItem | TextGraphicsItem:
        data = dict(element)
        element_type = str(data.get("type", "")).lower()
        data["name"] = self._prepare_element_name(data.get("name"), element_type)
        if element_type == "text":
            data["font"] = self._normalise_font_value(data.get("font"))
            item = create_text_item(data)
            self.addItem(item)
            item.apply_element(data)
            item.geometryCommitted.connect(self._on_geometry_committed)
            self.itemsChanged.emit()
            return item
        item = create_item(data)
        self.addItem(item)
        item.geometryCommitted.connect(self._on_geometry_committed)
        item.apply_element(data)
        self.itemsChanged.emit()
        return item

    def delete_item(self, item: GraphicsElementItem) -> None:
        self.removeItem(item)

    def remove_items(
        self, items: Iterable[GraphicsElementItem | TextGraphicsItem]
    ) -> bool:
        removed = False
        for item in list(items):
            if getattr(item, "_locked", False):
                continue
            self.removeItem(item)
            removed = True
        if removed:
            self.clearSelection()
            self.clear_guides()
            self.update()
            self.itemsChanged.emit()
        return removed

    def remove_selected_items(self) -> bool:
        return self.remove_items(self.selected_items())

    def can_remove_selected_items(self) -> bool:
        for item in self.selected_items():
            if getattr(item, "_locked", False):
                continue
            return True
        return False

    def can_duplicate_selected_items(self) -> bool:
        for item in self.selected_items():
            if getattr(item, "_locked", False):
                continue
            return True
        return False

    def duplicate_selected_items(self) -> bool:
        selected = [
            item for item in self.selected_items() if not getattr(item, "_locked", False)
        ]
        if not selected:
            return False

        # Offset duplicates by a single grid step (or a sensible default)
        offset_mm = self.grid_mm if self.grid_mm > 0 else 1.0
        new_items: list[GraphicsElementItem | TextGraphicsItem] = []
        for item in selected:
            element = item.to_dict()
            element.pop("id", None)
            element.pop("name", None)
            element["x_mm"] = float(element.get("x_mm", 0.0)) + offset_mm
            element["y_mm"] = float(element.get("y_mm", 0.0)) + offset_mm
            duplicate = self.add_element(element)
            new_items.append(duplicate)

        if not new_items:
            return False

        self.clearSelection()
        for item in new_items:
            item.setSelected(True)
        self.update()
        return True

    def set_selected_items_locked(self, locked: bool) -> bool:
        changed = False
        for item in self.selected_items():
            current = getattr(item, "_locked", False)
            if current == locked:
                continue
            if hasattr(item, "lock"):
                item.lock(locked)
            elif hasattr(item, "set_locked"):
                item.set_locked(locked)
            item.update()
            changed = True
        if changed:
            self.update()
        return changed

    def are_all_selected_locked(self) -> bool:
        selected = self.selected_items()
        if not selected:
            return False
        return all(getattr(item, "_locked", False) for item in selected)

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

    # ------------------------------------------------------------------
    def alignment_tolerance(self) -> float:
        """Return the snapping tolerance in pixels."""

        return float(self._alignment_tolerance)

    def set_alignment_tolerance(self, tolerance: float) -> None:
        """Update the snapping tolerance used for object alignment."""

        tolerance = max(0.0, float(tolerance))
        if math.isclose(tolerance, self._alignment_tolerance, rel_tol=0.0, abs_tol=1e-6):
            return
        self._alignment_tolerance = tolerance
        self.clear_guides()

    def clear_guides(self) -> None:
        for guide in self._guides:
            if _is_valid_graphics_item(guide):
                try:
                    self.removeItem(guide)
                except RuntimeError:  # pragma: no cover - defensive
                    pass
        self._guides.clear()

    # ------------------------------------------------------------------
    def _align_rect(self, item: GraphicsElementItem, rect: QRectF) -> QRectF:
        tolerance = self._alignment_tolerance
        best_rect = QRectF(rect)
        best_diff_x = tolerance
        best_diff_y = tolerance
        vertical_guides: list[float] = []
        horizontal_guides: list[float] = []

        for other in self._iter_editable_items():
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
    def _on_geometry_committed(
        self, item: GraphicsElementItem | TextGraphicsItem, before, after
    ) -> None:
        command = _StateChange(item, before, after, "Mover elemento")
        self._push_command(command)

    def change_property(
        self, item: GraphicsElementItem | TextGraphicsItem, name: str, value: Any
    ) -> None:
        current = copy.deepcopy(item.element.get(name))
        if name == "font":
            current = self._normalise_font_value(current)
            value = self._normalise_font_value(value)
        if current == value:
            return
        command = _PropertyChange(item, name, current, value)
        self._push_command(command)

    # ------------------------------------------------------------------
    def font_metadata_for(self, font_id: str) -> dict[str, Any] | None:
        if font_id in self._metadata_fonts:
            return dict(self._metadata_fonts[font_id])
        entry = font_store.metadata_for(font_id)
        if entry:
            self._metadata_fonts[font_id] = dict(entry)
            return dict(entry)
        return None

    def export_fonts(self, font_ids: set[str]) -> dict[str, Any]:
        fonts: dict[str, Any] = {}
        for font_id in font_ids:
            entry = self.font_metadata_for(font_id)
            if entry:
                fonts[font_id] = entry
        return fonts

    def _find_font_by_filename(self, filename: str) -> dict[str, Any] | None:
        target = Path(filename).name.lower()
        for font_id, entry in self._metadata_fonts.items():
            name = str(entry.get("filename") or "")
            if name and Path(name).name.lower() == target:
                return {"id": font_id, "filename": name}
        return None

    def _normalise_font_value(self, value: Any) -> dict[str, Any]:
        font = dict(value) if isinstance(value, Mapping) else {}
        ttf_value = font.get("ttf")
        if isinstance(ttf_value, Mapping):
            font_id = str(ttf_value.get("id", ""))
            filename = ttf_value.get("filename")
            if font_id:
                entry = self.font_metadata_for(font_id)
                if entry:
                    font_store.register_metadata({font_id: entry})
                    filename = filename or entry.get("filename")
                families = font_store.ensure_qt_font(font_id)
                if families and not font.get("family"):
                    font["family"] = families[0]
                font_spec = {"id": font_id}
                if filename:
                    font_spec["filename"] = str(filename)
                font["ttf"] = font_spec
                if entry:
                    self._metadata_fonts[font_id] = dict(entry)
                    self.metadata.setdefault("fonts", {})[font_id] = dict(entry)
            else:
                font["ttf"] = None
            return font
        if isinstance(ttf_value, (str, Path)) and ttf_value:
            path = Path(ttf_value)
            if path.exists():
                font_id, _ = font_store.register_file(path)
                entry = font_store.metadata_for(font_id) or {}
                if entry:
                    self._metadata_fonts[font_id] = dict(entry)
                    self.metadata.setdefault("fonts", {})[font_id] = dict(entry)
                families = entry.get("families") or font_store.ensure_qt_font(font_id)
                if families and not font.get("family"):
                    font["family"] = families[0]
                filename = entry.get("filename", path.name)
                font["ttf"] = {"id": font_id, "filename": filename}
            else:
                existing = self._find_font_by_filename(str(ttf_value))
                if existing:
                    font_id = existing["id"]
                    entry = self.font_metadata_for(font_id)
                    if entry:
                        self.metadata.setdefault("fonts", {})[font_id] = dict(entry)
                    families = font_store.ensure_qt_font(font_id)
                    if families and not font.get("family"):
                        font["family"] = families[0]
                    font["ttf"] = existing
                else:
                    font["ttf"] = None
            return font
        if ttf_value in (None, ""):
            font["ttf"] = None
        return font

    # ------------------------------------------------------------------
    def to_template(
        self,
        name: str,
        variables: Mapping[str, Any] | None = None,
    ) -> TemplateDocument:
        return build_model_from_scene(self, name, variables)

    def load_document(self, document: TemplateDocument) -> None:
        self.clear()
        self._base_rect = None
        self.metadata = dict(getattr(document, "metadata", {}))
        fonts_metadata = self.metadata.get("fonts")
        if isinstance(fonts_metadata, Mapping):
            self._metadata_fonts = {
                str(font_id): dict(spec)
                for font_id, spec in fonts_metadata.items()
                if isinstance(font_id, str) and isinstance(spec, Mapping)
            }
            font_store.register_metadata(self._metadata_fonts)
        else:
            self._metadata_fonts = {}
        self.page = document.page
        self._dots_per_mm = _compute_dots_per_mm(self.page)
        self._update_scene_rect()
        for element in document.elements:
            self.add_element(element)
        if not document.elements:
            self.itemsChanged.emit()
        self.undo_stack.clear()
        self.reset_history_snapshots()

    # ------------------------------------------------------------------
    def selected_items(self) -> list[GraphicsElementItem | TextGraphicsItem]:
        selected: list[GraphicsElementItem | TextGraphicsItem] = []
        for item in self.selectedItems():
            if isinstance(item, (GraphicsElementItem, TextGraphicsItem)):
                selected.append(item)
        return selected

    def bring_to_front(self) -> None:
        selected = self.selected_items()
        for index, item in enumerate(selected, start=1):
            item.setZValue(item.zValue() + 10 * index)
        if selected:
            self.itemsChanged.emit()

    def send_to_back(self) -> None:
        selected = self.selected_items()
        for index, item in enumerate(selected, start=1):
            item.setZValue(item.zValue() - 10 * index)
        if selected:
            self.itemsChanged.emit()

    def reorder_items(
        self, order: list[GraphicsElementItem | TextGraphicsItem]
    ) -> None:
        """Apply ``order`` as the stacking sequence for editable items."""

        total = len(order)
        if total <= 1:
            return
        for position, item in enumerate(order):
            # Highest z-value should appear first in ``order``
            item.setZValue(float(total - position))
        self.itemsChanged.emit()

    # ------------------------------------------------------------------
    def unique_name(
        self,
        proposed: str | None,
        *,
        element_type: str | None = None,
        exclude: GraphicsElementItem | TextGraphicsItem | None = None,
    ) -> str:
        """Return a name unique among the editable items."""

        base = (proposed or "").strip()
        if not base:
            base = self.default_name(element_type)

        existing = {
            str(item.element.get("name", "")).strip()
            for item in self._iter_editable_items()
            if item is not exclude
        }
        if base not in existing:
            return base

        suffix = 2
        while True:
            candidate = f"{base} ({suffix})"
            if candidate not in existing:
                return candidate
            suffix += 1

    def default_name(self, element_type: str | None) -> str:
        return self._default_name_map.get(element_type or "", "Elemento")

    def _prepare_element_name(
        self, proposed: str | None, element_type: str | None
    ) -> str:
        return self.unique_name(proposed, element_type=element_type)

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

    def align_center(self) -> None:
        selected = self.selected_items()
        if not selected:
            return
        min_left = min(item.pos().x() for item in selected)
        max_right = max(item.pos().x() + item.shapeRect().width() for item in selected)
        center = (min_left + max_right) / 2.0
        for item in selected:
            width = item.shapeRect().width()
            item.setX(center - width / 2.0)

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
        item: GraphicsElementItem | TextGraphicsItem,
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

