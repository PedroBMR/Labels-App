"""Property helpers for editor items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Property:
    """Store metadata about an editable property."""

    name: str
    value: Any | None = None
    editable: bool = True

    def set_value(self, value: Any | None) -> None:
        """Update the property value."""

        if not self.editable:
            msg = f"Property '{self.name}' is read-only"
            raise ValueError(msg)
        self.value = value

    def to_dict(self) -> dict[str, Any | None]:
        """Return a serialisable representation of the property."""

        return {"name": self.name, "value": self.value, "editable": self.editable}
