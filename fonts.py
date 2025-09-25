"""Helpers for managing embedded fonts used by templates."""

from __future__ import annotations

import base64
import hashlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:  # pragma: no cover - optional during headless tests
    from qt_compat import QByteArray, QFontDatabase
except Exception:  # pragma: no cover - fallback when Qt bindings missing
    QFontDatabase = None  # type: ignore[assignment]
    QByteArray = None  # type: ignore[assignment]

__all__ = ["EmbeddedFontStore", "font_store"]


def _normalise_font_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    filename = data.get("filename")
    if isinstance(filename, str):
        entry["filename"] = filename
    payload = data.get("data")
    if isinstance(payload, str) and payload:
        entry["data"] = payload
    families = data.get("families")
    if isinstance(families, Mapping):  # pragma: no cover - defensive
        families = list(families.values())
    if isinstance(families, (list, tuple)):
        entry["families"] = [str(fam) for fam in families if isinstance(fam, str)]
    return entry


@dataclass
class EmbeddedFontStore:
    """In-memory cache for fonts embedded in templates."""

    _fonts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _qt_loaded: set[str] = field(default_factory=set)
    _paths: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def register_metadata(self, fonts: Mapping[str, Any]) -> None:
        """Register fonts described by template metadata."""

        for font_id, payload in fonts.items():
            if not isinstance(font_id, str) or not font_id:
                continue
            if not isinstance(payload, Mapping):
                continue
            entry = self._fonts.setdefault(font_id, {})
            entry.update(_normalise_font_entry(payload))

    # ------------------------------------------------------------------
    def has_font(self, font_id: str) -> bool:
        return font_id in self._fonts and bool(self._fonts[font_id].get("data"))

    # ------------------------------------------------------------------
    def register_file(self, path: str | Path) -> tuple[str, dict[str, Any]]:
        """Register ``path`` as an embedded font and return its id."""

        source = Path(path)
        if not source.exists():  # pragma: no cover - defensive
            raise FileNotFoundError(str(source))
        payload = source.read_bytes()
        font_id = hashlib.sha1(payload).hexdigest()
        encoded = base64.b64encode(payload).decode("ascii")
        entry = {
            "filename": source.name,
            "data": encoded,
        }
        self._fonts[font_id] = entry
        self._qt_loaded.discard(font_id)
        self._paths.pop(font_id, None)
        families = self.ensure_qt_font(font_id)
        if families:
            entry["families"] = families
        return font_id, entry

    # ------------------------------------------------------------------
    def ensure_qt_font(self, font_id: str) -> list[str]:
        """Ensure ``font_id`` is registered with Qt returning its families."""

        entry = self._fonts.get(font_id)
        if not entry or not entry.get("data"):
            return []
        if font_id in self._qt_loaded or QFontDatabase is None or QByteArray is None:
            return [str(f) for f in entry.get("families", [])]
        payload = base64.b64decode(entry["data"])
        font_index = QFontDatabase.addApplicationFontFromData(QByteArray(payload))
        if font_index >= 0:
            families = [str(name) for name in QFontDatabase.applicationFontFamilies(font_index)]
        else:  # pragma: no cover - depends on Qt availability
            families = []
        if families:
            entry["families"] = families
        self._qt_loaded.add(font_id)
        return families

    # ------------------------------------------------------------------
    def ensure_path(self, font_id: str) -> str | None:
        """Return a filesystem path for ``font_id`` creating a temp file."""

        entry = self._fonts.get(font_id)
        if not entry or not entry.get("data"):
            return None
        if font_id in self._paths:
            return self._paths[font_id]
        payload = base64.b64decode(entry["data"])
        suffix = Path(entry.get("filename") or "font.ttf").suffix or ".ttf"
        with tempfile.NamedTemporaryFile(
            prefix="font-", suffix=suffix, delete=False
        ) as handle:
            handle.write(payload)
            path = handle.name
        self._paths[font_id] = path
        return path

    # ------------------------------------------------------------------
    def resolve_spec_path(self, spec: Any) -> str | None:
        """Resolve ``spec`` (string or mapping) into a filesystem path."""

        if isinstance(spec, Mapping):
            font_id = spec.get("id")
            if isinstance(font_id, str) and font_id:
                return self.ensure_path(font_id)
        elif isinstance(spec, (str, Path)):
            return str(spec)
        return None

    # ------------------------------------------------------------------
    def metadata_for(self, font_id: str) -> dict[str, Any] | None:
        entry = self._fonts.get(font_id)
        if not entry or not entry.get("data"):
            return None
        result = {
            "filename": entry.get("filename"),
            "data": entry.get("data"),
        }
        if entry.get("families"):
            result["families"] = list(entry["families"])
        return result

    # ------------------------------------------------------------------
    def export_fonts(self, font_ids: Mapping[str, Any] | set[str] | list[str]) -> dict[str, Any]:
        """Return metadata for the provided ``font_ids``."""

        result: dict[str, Any] = {}
        for font_id in font_ids:
            if not isinstance(font_id, str):
                continue
            entry = self.metadata_for(font_id)
            if entry:
                result[font_id] = entry
        return result


font_store = EmbeddedFontStore()

