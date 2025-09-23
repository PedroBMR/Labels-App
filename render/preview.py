"""Plain-text preview helpers for editor items."""

from __future__ import annotations

from typing import Iterable

from editor.items.base import EditorItem


def render_preview(items: Iterable[EditorItem]) -> str:
    """Return a simple textual preview for a sequence of items."""

    lines: list[str] = []
    for item in items:
        data = item.to_dict()
        identifier = data["id"]
        properties = data.get("properties", {})
        summary = ", ".join(
            f"{key}={value!r}" for key, value in sorted(properties.items())
        )
        lines.append(f"{identifier}: {summary}" if summary else identifier)
    return "\n".join(lines)
