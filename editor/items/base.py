"""Basic data structures for editor items."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class EditorItem:
    """Represents an editable element within the label editor."""

    identifier: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def set_property(self, name: str, value: Any) -> None:
        """Store or update a property on the item."""

        self.properties[name] = value

    def get_property(self, name: str, default: Any | None = None) -> Any:
        """Return a property value if present."""

        return self.properties.get(name, default)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialisable representation of the item."""

        return {"id": self.identifier, "properties": dict(self.properties)}
