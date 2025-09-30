from __future__ import annotations

import json
import sys
import types
from pathlib import Path

if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module

import pytest

from db import store
from utils.fs import canonical_path as canonical_file_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "app.sqlite"


def test_upsert_template_insert_and_update(db_path: Path, tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text("{}", encoding="utf-8")

    store.upsert_template(
        name="Shipping",
        data="{}",
        path=template_path,
        file_hash="hash-one",
        width_mm=50.0,
        height_mm=30.0,
        dpi=203,
        kind="tspl",
        tags=["alpha", "beta"],
        updated_at="2024-01-01T00:00:00+00:00",
        db_path=db_path,
    )

    template_id = store.get_template_id_by_name("Shipping", db_path=db_path)
    assert isinstance(template_id, int)

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            (
                "SELECT name, kind, path, file_hash, width_mm, height_mm, dpi, "
                "tags, updated_at, data FROM templates WHERE id = ?"
            ),
            (template_id,),
        ).fetchone()

    assert row is not None
    assert row["name"] == "Shipping"
    assert row["kind"] == "tspl"
    assert Path(row["path"]) == canonical_file_path(template_path)
    assert row["file_hash"] == "hash-one"
    assert row["width_mm"] == 50.0
    assert row["height_mm"] == 30.0
    assert row["dpi"] == 203
    assert json.loads(row["tags"]) == ["alpha", "beta"]
    assert row["updated_at"] == "2024-01-01T00:00:00+00:00"
    assert row["data"] == "{}"

    store.upsert_template(
        name="Shipping",
        data="{\"updated\": true}",
        path=template_path,
        file_hash="hash-two",
        width_mm=60.0,
        height_mm=40.0,
        dpi=300,
        kind="zpl",
        tags=["gamma"],
        updated_at="2024-02-02T00:00:00+00:00",
        db_path=db_path,
    )

    updated_id = store.get_template_id_by_name("Shipping", db_path=db_path)
    assert updated_id == template_id

    with store.get_conn(db_path) as conn:
        updated_row = conn.execute(
            (
                "SELECT kind, file_hash, width_mm, height_mm, dpi, tags, "
                "updated_at, data FROM templates WHERE id = ?"
            ),
            (template_id,),
        ).fetchone()

    assert updated_row is not None
    assert updated_row["kind"] == "zpl"
    assert updated_row["file_hash"] == "hash-two"
    assert updated_row["width_mm"] == 60.0
    assert updated_row["height_mm"] == 40.0
    assert updated_row["dpi"] == 300
    assert json.loads(updated_row["tags"]) == ["gamma"]
    assert updated_row["updated_at"] == "2024-02-02T00:00:00+00:00"
    assert updated_row["data"] == "{\"updated\": true}"


def test_upsert_asset_round_trip(db_path: Path, tmp_path: Path) -> None:
    asset_path = tmp_path / "logo.png"
    asset_path.write_bytes(b"binary")

    store.upsert_asset(
        name="Logo",
        kind="image",
        data=b"binary",
        path=asset_path,
        file_hash="asset-one",
        width_px=128,
        height_px=64,
        dpi_x=203,
        dpi_y=203,
        tags=["brand"],
        updated_at="2024-03-03T12:00:00+00:00",
        db_path=db_path,
    )

    asset_id = store.get_asset_id_by_hash("asset-one", db_path=db_path)
    assert isinstance(asset_id, int)

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            (
                "SELECT name, kind, path, file_hash, width_px, height_px, dpi_x, "
                "dpi_y, tags, data, updated_at FROM assets WHERE id = ?"
            ),
            (asset_id,),
        ).fetchone()

    assert row is not None
    assert row["name"] == "Logo"
    assert row["kind"] == "image"
    assert Path(row["path"]) == canonical_file_path(asset_path)
    assert row["file_hash"] == "asset-one"
    assert row["width_px"] == 128
    assert row["height_px"] == 64
    assert row["dpi_x"] == 203.0
    assert row["dpi_y"] == 203.0
    assert json.loads(row["tags"]) == ["brand"]
    assert row["data"] == b"binary"
    assert row["updated_at"] == "2024-03-03T12:00:00+00:00"

    store.upsert_asset(
        name="Logo",
        kind="image",
        data=b"new",
        path=asset_path,
        file_hash="asset-two",
        width_px=256,
        height_px=128,
        dpi_x=300,
        dpi_y=300,
        tags=[],
        updated_at="2024-04-04T12:00:00+00:00",
        db_path=db_path,
    )

    updated_asset_id = store.get_asset_id_by_hash("asset-two", db_path=db_path)
    assert updated_asset_id == asset_id

    with store.get_conn(db_path) as conn:
        updated_row = conn.execute(
            (
                "SELECT file_hash, width_px, height_px, dpi_x, dpi_y, tags, data, "
                "updated_at FROM assets WHERE id = ?"
            ),
            (asset_id,),
        ).fetchone()

    assert updated_row is not None
    assert updated_row["file_hash"] == "asset-two"
    assert updated_row["width_px"] == 256
    assert updated_row["height_px"] == 128
    assert updated_row["dpi_x"] == 300.0
    assert updated_row["dpi_y"] == 300.0
    assert updated_row["tags"] is None
    assert updated_row["data"] == b"new"
    assert updated_row["updated_at"] == "2024-04-04T12:00:00+00:00"


def test_raster_cache_insert_and_update(db_path: Path, tmp_path: Path) -> None:
    store.upsert_asset(
        name="Asset",
        kind="image",
        data=b"payload",
        path=None,
        file_hash="hash",
        width_px=10,
        height_px=10,
        dpi_x=203,
        dpi_y=203,
        db_path=db_path,
    )

    asset_id = store.get_asset_id_by_hash("hash", db_path=db_path)
    assert asset_id is not None

    cache_path = tmp_path / "cache.bin"
    cache_path.write_bytes(b"cached")

    stored_path = store.insert_or_get_raster_cache(
        asset_id=asset_id,
        width_dots=160,
        height_dots=80,
        dpi=(203, 203),
        dither="floyd",
        gamma=None,
        sharpen=False,
        invert=False,
        threshold=128,
        cache_path=cache_path,
        db_path=db_path,
    )

    assert stored_path == canonical_file_path(cache_path)

    located = store.find_raster_cache(
        asset_id,
        160,
        80,
        (203, 203),
        "floyd",
        0.0,
        False,
        False,
        128,
        db_path=db_path,
    )
    assert located == canonical_file_path(cache_path)

    updated_path = tmp_path / "cache-updated.bin"
    updated_path.write_bytes(b"cached-updated")

    stored_again = store.insert_or_get_raster_cache(
        asset_id=asset_id,
        width_dots=160,
        height_dots=80,
        dpi=(203, 203),
        dither="floyd",
        gamma=0.0,
        sharpen=False,
        invert=False,
        threshold=128,
        cache_path=updated_path,
        db_path=db_path,
    )

    assert stored_again == canonical_file_path(updated_path)

    with store.get_conn(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM raster_cache").fetchone()[0]
    assert count == 1

    refreshed = store.find_raster_cache(
        asset_id,
        160,
        80,
        (203, 203),
        "floyd",
        0.0,
        False,
        False,
        128,
        db_path=db_path,
    )
    assert refreshed == canonical_file_path(updated_path)
