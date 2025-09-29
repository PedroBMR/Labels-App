from __future__ import annotations

from pathlib import Path
import sys
import types

if "PIL" not in sys.modules:  # pragma: no cover - test isolation helper
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("Image")

    class _Resampling:
        LANCZOS = 1

    image_module.Resampling = _Resampling
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module

from db import store
from editor.preset_manager import PresetManager


def _setup_template(tmp_path: Path) -> tuple[Path, int]:
    db_path = tmp_path / "app.sqlite"
    store.init(db_path)
    store.upsert_template(
        name="PresetDoc",
        data="{}",
        path=None,
        file_hash="hash",
        width_mm=50.0,
        height_mm=30.0,
        dpi=203,
        db_path=db_path,
    )
    template_id = store.get_template_id_by_name("PresetDoc", db_path=db_path)
    assert template_id is not None
    return db_path, template_id


def test_preset_manager_rename_and_delete(tmp_path):
    db_path, template_id = _setup_template(tmp_path)
    manager = PresetManager(template_id, db_path=db_path)
    manager.save_preset("Inicial", {"foo": "bar"})

    presets = manager.list_presets()
    assert [preset["name"] for preset in presets] == ["Inicial"]

    assert manager.rename_preset("Inicial", "Renomeado")
    renamed = manager.list_presets()
    assert [preset["name"] for preset in renamed] == ["Renomeado"]

    data = manager.load_preset("Renomeado")
    assert isinstance(data, dict)
    assert data == {"foo": "bar"}
    assert manager.load_preset("Inicial") is None

    assert manager.delete_preset("Renomeado")
    assert manager.list_presets() == []


def test_rename_missing_preset_returns_false(tmp_path):
    db_path, template_id = _setup_template(tmp_path)
    manager = PresetManager(template_id, db_path=db_path)
    assert manager.rename_preset("Inexistente", "Novo") is False
