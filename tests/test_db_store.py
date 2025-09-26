from __future__ import annotations

import json
from pathlib import Path

from db import migrations, store
from utils.fs import canonical_path as canonical_file_path


def test_init_creates_schema(tmp_path):
    db_path = tmp_path / "app.sqlite"

    store.init(db_path)

    with store.get_conn(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "meta",
            "templates",
            "assets",
            "raster_cache",
            "print_jobs",
            "vars_presets",
        }.issubset(tables)

        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        assert row is not None
        assert row[0] == str(migrations.SCHEMA_VERSION)

    # Second initialisation should be a no-op
    store.init(db_path)

    with store.get_conn(db_path) as conn:
        value = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        assert value is not None
        assert value[0] == str(migrations.SCHEMA_VERSION)


def test_upsert_template_persists_metadata(tmp_path):
    db_path = tmp_path / "app.sqlite"
    template_path = tmp_path / "template.json"

    store.upsert_template(
        name="example",
        data="{}",
        path=template_path,
        file_hash="abc123",
        width_mm=42.0,
        height_mm=21.0,
        dpi=203,
        kind="tspl",
        tags=["shipping", "demo"],
        updated_at="2024-01-01T00:00:00+00:00",
        db_path=db_path,
    )

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT name, kind, path, file_hash, width_mm, height_mm, dpi, tags, updated_at"
            " FROM templates WHERE name = ?",
            ("example",),
        ).fetchone()

    assert row is not None
    assert row["kind"] == "tspl"
    assert Path(row["path"]) == canonical_file_path(template_path)
    assert row["file_hash"] == "abc123"
    assert row["width_mm"] == 42.0
    assert row["height_mm"] == 21.0
    assert row["dpi"] == 203
    assert json.loads(row["tags"]) == ["shipping", "demo"]
    assert row["updated_at"] == "2024-01-01T00:00:00+00:00"

    store.upsert_template(
        name="example",
        data="{\"v\": 1}",
        path=template_path,
        file_hash="xyz789",
        width_mm=50.0,
        height_mm=30.0,
        dpi=300,
        kind="zpl",
        tags=["updated"],
        updated_at="2024-02-02T00:00:00+00:00",
        db_path=db_path,
    )

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT kind, file_hash, width_mm, height_mm, dpi, tags, updated_at"
            " FROM templates WHERE name = ?",
            ("example",),
        ).fetchone()

    assert row is not None
    assert row["kind"] == "zpl"
    assert row["file_hash"] == "xyz789"
    assert row["width_mm"] == 50.0
    assert row["height_mm"] == 30.0
    assert row["dpi"] == 300
    assert json.loads(row["tags"]) == ["updated"]
    assert row["updated_at"] == "2024-02-02T00:00:00+00:00"


def test_upsert_asset_persists_metadata(tmp_path):
    db_path = tmp_path / "app.sqlite"
    asset_path = tmp_path / "logo.png"

    store.upsert_asset(
        name="logo",
        kind="image",
        data=b"binary",
        path=asset_path,
        file_hash="hash1",
        width_px=128,
        height_px=256,
        dpi_x=203,
        dpi_y=203,
        tags=["brand"],
        updated_at="2024-03-01T12:00:00+00:00",
        db_path=db_path,
    )

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT name, kind, path, file_hash, width_px, height_px, dpi_x, dpi_y, tags, data, updated_at"
            " FROM assets WHERE name = ?",
            ("logo",),
        ).fetchone()

    assert row is not None
    assert row["kind"] == "image"
    assert Path(row["path"]) == canonical_file_path(asset_path)
    assert row["file_hash"] == "hash1"
    assert row["width_px"] == 128
    assert row["height_px"] == 256
    assert row["dpi_x"] == 203.0
    assert row["dpi_y"] == 203.0
    assert json.loads(row["tags"]) == ["brand"]
    assert row["data"] == b"binary"
    assert row["updated_at"] == "2024-03-01T12:00:00+00:00"

    store.upsert_asset(
        name="logo",
        kind="image",
        data=b"new",
        path=asset_path,
        file_hash="hash2",
        width_px=64,
        height_px=64,
        dpi_x=150,
        dpi_y=150,
        tags=[],
        updated_at="2024-04-01T12:00:00+00:00",
        db_path=db_path,
    )

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT file_hash, width_px, height_px, dpi_x, dpi_y, tags, data, updated_at"
            " FROM assets WHERE name = ?",
            ("logo",),
        ).fetchone()

    assert row is not None
    assert row["file_hash"] == "hash2"
    assert row["width_px"] == 64
    assert row["height_px"] == 64
    assert row["dpi_x"] == 150.0
    assert row["dpi_y"] == 150.0
    assert row["tags"] is None
    assert row["data"] == b"new"
    assert row["updated_at"] == "2024-04-01T12:00:00+00:00"
