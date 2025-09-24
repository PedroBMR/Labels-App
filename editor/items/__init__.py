"""Factory helpers for editor graphics items."""

from __future__ import annotations

from typing import Any, Mapping

from .base import GraphicsElementItem, iter_element_items

__all__ = ["GraphicsElementItem", "create_item", "iter_element_items"]


def create_item(element: Mapping[str, Any]) -> GraphicsElementItem:
    """Instantiate a :class:`GraphicsElementItem` from ``element``."""

    return GraphicsElementItem(element)
