"""Helpers for listing and mutating variable presets for a template."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from db import store

__all__ = ["PresetManager"]


class PresetManager:
    """High level helper orchestrating preset operations for a template."""

    def __init__(
        self, template_id: int, *, db_path: str | Path | None = None
    ) -> None:
        self._template_id = int(template_id)
        self._db_path = db_path

    # ------------------------------------------------------------------
    def list_presets(self) -> list[dict[str, Any]]:
        """Return all presets stored for the managed template."""

        return store.list_vars_presets(
            template_id=self._template_id, db_path=self._db_path
        )

    # ------------------------------------------------------------------
    def delete_preset(self, name: str) -> bool:
        """Delete ``name`` returning ``True`` when the preset existed."""

        cleaned = name.strip()
        if not cleaned:
            return False
        return store.delete_vars_preset(
            template_id=self._template_id, name=cleaned, db_path=self._db_path
        )

    # ------------------------------------------------------------------
    def rename_preset(self, old_name: str, new_name: str) -> bool:
        """Rename a preset keeping its stored data intact."""

        cleaned = new_name.strip()
        if not cleaned:
            return False
        if cleaned == old_name:
            return True

        data = store.load_vars_preset(
            template_id=self._template_id,
            name=old_name,
            db_path=self._db_path,
        )
        if data is None:
            return False
        store.save_vars_preset(
            template_id=self._template_id,
            name=cleaned,
            data=data,
            db_path=self._db_path,
        )
        store.delete_vars_preset(
            template_id=self._template_id,
            name=old_name,
            db_path=self._db_path,
        )
        return True

    # ------------------------------------------------------------------
    def load_preset(
        self, name: str
    ) -> Mapping[str, Any] | Sequence[object] | None:
        """Return the stored payload for ``name`` if it exists."""

        cleaned = name.strip()
        if not cleaned:
            return None
        return store.load_vars_preset(
            template_id=self._template_id,
            name=cleaned,
            db_path=self._db_path,
        )

    # ------------------------------------------------------------------
    def save_preset(
        self, name: str, data: Mapping[str, Any] | Sequence[object] | str
    ) -> None:
        """Persist ``data`` under ``name``."""

        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Preset name must not be empty")
        store.save_vars_preset(
            template_id=self._template_id,
            name=cleaned,
            data=data,
            db_path=self._db_path,
        )
