import sys
import types
from pathlib import Path

import pytest

if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module

from db import store


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "app.sqlite"


def test_vars_presets_crud_roundtrip(db_path: Path) -> None:
    template_id = 42
    preset_name = "Shipping"
    initial_payload = {"name": "Alice", "items": [1, {"nested": True}]}

    store.save_vars_preset(
        template_id=template_id,
        name=preset_name,
        data=initial_payload,
        db_path=db_path,
    )

    loaded = store.load_vars_preset(
        template_id=template_id, name=preset_name, db_path=db_path
    )
    assert loaded == initial_payload

    presets = store.list_vars_presets(template_id=template_id, db_path=db_path)
    assert len(presets) == 1
    assert presets[0]["template_id"] == template_id
    assert presets[0]["name"] == preset_name
    assert presets[0]["data"] == initial_payload

    json_payload = "{\"count\": 3, \"enabled\": true}"
    store.save_vars_preset(
        template_id=template_id,
        name=preset_name,
        data=json_payload,
        db_path=db_path,
    )

    updated = store.load_vars_preset(
        template_id=template_id, name=preset_name, db_path=db_path
    )
    assert updated == {"count": 3, "enabled": True}

    all_presets = store.list_vars_presets(db_path=db_path)
    assert len(all_presets) == 1
    assert all_presets[0]["data"] == {"count": 3, "enabled": True}

    assert store.delete_vars_preset(
        template_id=template_id, name=preset_name, db_path=db_path
    )
    assert store.load_vars_preset(
        template_id=template_id, name=preset_name, db_path=db_path
    ) is None
    assert (
        store.list_vars_presets(template_id=template_id, db_path=db_path)
        == []
    )
    assert (
        store.delete_vars_preset(
            template_id=template_id, name=preset_name, db_path=db_path
        )
        is False
    )


def test_printer_profile_staged_updates_normalisation(db_path: Path) -> None:
    profile_name = "Thermal"
    initial_settings = {
        "media_gap_mm": "2.5",
        "media_mark_mm": "4.0",
        "media_gap_offset_mm": "",
        "media_print_rate": 0,
        "media_speed": "0",
        "media_darkness": "7",
        "media_calibrate_next": True,
    }

    store.save_printer_profile(
        profile_name,
        initial_settings,
        db_path=db_path,
    )

    partial_update = {
        "media_mark_mm": "5.5",
        "media_speed": "24",
        "media_darkness": "0",
    }

    store.save_printer_profile(
        profile_name,
        partial_update,
        db_path=db_path,
    )

    loaded = store.load_printer_profile(profile_name, db_path=db_path)
    assert loaded is not None

    assert loaded["media_gap_mm"] == 2.5
    assert loaded["media_mark_mm"] == 5.5
    assert isinstance(loaded["media_gap_mm"], float)
    assert isinstance(loaded["media_mark_mm"], float)
    assert loaded["media_gap_offset_mm"] == 0.0
    assert loaded["media_mark_offset_mm"] == 0.0
    assert loaded["media_fine_offset_mm"] == 0.0
    assert isinstance(loaded["media_gap_offset_mm"], float)
    assert loaded["media_speed"] == 24
    assert isinstance(loaded["media_speed"], int)
    assert "media_darkness" not in loaded
    assert "media_print_rate" not in loaded
    assert loaded["media_calibrate_next"] is True
