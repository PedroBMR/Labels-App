"""Factory helpers for editor graphics items."""

from __future__ import annotations

from typing import Any, Mapping

from qt_compat import QGraphicsItem, QGraphicsRectItem, QRectF, Qt

from .base import GraphicsElementItem, iter_element_items
from .text import EditableTextItem, TextGraphicsItem

__all__ = [
    "GraphicsElementItem",
    "EditableTextItem",
    "TextGraphicsItem",
    "create_base_rect_item",
    "create_item",
    "create_text_item",
    "iter_element_items",
]


def create_item(element: Mapping[str, Any]) -> GraphicsElementItem:
    """Instantiate a :class:`GraphicsElementItem` from ``element``."""

    return GraphicsElementItem(element)


def _configure_item_flags(item: QGraphicsItem) -> None:
    item.setFlag(QGraphicsItem.ItemIsMovable, True)
    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
    item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
    item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)


def create_base_rect_item(rect: QRectF) -> QGraphicsRectItem:
    """Create a base rectangle matching ``rect`` with common flags applied."""

    item = QGraphicsRectItem(rect)
    _configure_item_flags(item)
    item.setBrush(Qt.white)
    return item


def create_text_item(element: Mapping[str, Any] | None = None) -> TextGraphicsItem:
    """Create a :class:`TextGraphicsItem` applying default flags."""

    return TextGraphicsItem(element)
