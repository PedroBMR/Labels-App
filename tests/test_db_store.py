from __future__ import annotations

import json
import sqlite3
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
            "printer_profiles",
        }.issubset(tables)

        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        assert row is not None
        assert row[0] == str(migrations.SCHEMA_VERSION)

        columns = {
            info[1]
            for info in conn.execute("PRAGMA table_info(print_jobs)").fetchall()
        }
        assert {
            "payload_hash",
            "payload",
            "pending_at",
            "running_at",
            "finished_at",
            "failed_at",
            "error_text",
        }.issubset(columns)

    # Second initialisation should be a no-op
    store.init(db_path)

    with store.get_conn(db_path) as conn:
        value = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        assert value is not None
        assert value[0] == str(migrations.SCHEMA_VERSION)


def test_migration_upgrades_legacy_raster_cache(tmp_path):
    db_path = tmp_path / "legacy.sqlite"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE raster_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                width_px INTEGER NOT NULL,
                height_px INTEGER NOT NULL,
                dpi_x INTEGER NOT NULL,
                dpi_y INTEGER NOT NULL,
                dither TEXT NOT NULL,
                gamma REAL NOT NULL DEFAULT 0,
                sharpen INTEGER NOT NULL,
                invert INTEGER NOT NULL,
                threshold INTEGER NOT NULL,
                path TEXT NOT NULL
            )
            """
        )
        conn.commit()

    store.init(db_path)

    with store.get_conn(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(raster_cache)").fetchall()
        }

    assert "width_dots" in columns
    assert "height_dots" in columns
    assert "cache_path" in columns
    assert "width_px" not in columns
    assert "path" not in columns


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


def test_vars_presets_crud(tmp_path):
    db_path = tmp_path / "app.sqlite"

    store.upsert_template(
        name="TemplateA",
        data="{}",
        path=None,
        file_hash="hashA",
        width_mm=None,
        height_mm=None,
        dpi=None,
        db_path=db_path,
    )
    store.upsert_template(
        name="TemplateB",
        data="{}",
        path=None,
        file_hash="hashB",
        width_mm=None,
        height_mm=None,
        dpi=None,
        db_path=db_path,
    )

    template_a_id = store.get_template_id_by_name("TemplateA", db_path=db_path)
    template_b_id = store.get_template_id_by_name("TemplateB", db_path=db_path)

    assert template_a_id is not None
    assert template_b_id is not None
    assert store.get_template_id_by_name("Missing", db_path=db_path) is None

    store.save_vars_preset(
        template_id=template_a_id,
        name="Default",
        data={"foo": "bar"},
        db_path=db_path,
    )

    loaded = store.load_vars_preset(
        template_id=template_a_id,
        name="Default",
        db_path=db_path,
    )
    assert loaded == {"foo": "bar"}

    store.save_vars_preset(
        template_id=template_a_id,
        name="Default",
        data={"foo": "updated"},
        db_path=db_path,
    )

    updated = store.load_vars_preset(
        template_id=template_a_id,
        name="Default",
        db_path=db_path,
    )
    assert updated == {"foo": "updated"}

    store.save_vars_preset(
        template_id=template_b_id,
        name="Default",
        data={"bar": 1},
        db_path=db_path,
    )

    presets_a = store.list_vars_presets(template_id=template_a_id, db_path=db_path)
    assert [preset["name"] for preset in presets_a] == ["Default"]
    assert presets_a[0]["data"] == {"foo": "updated"}

    all_presets = store.list_vars_presets(db_path=db_path)
    assert {preset["template_id"] for preset in all_presets} == {
        template_a_id,
        template_b_id,
    }

    assert store.delete_vars_preset(
        template_id=template_a_id, name="Default", db_path=db_path
    )
    assert not store.delete_vars_preset(
        template_id=template_a_id, name="Default", db_path=db_path
    )
    assert (
        store.load_vars_preset(
            template_id=template_a_id, name="Default", db_path=db_path
        )
        is None
    )

    remaining = store.list_vars_presets(db_path=db_path)
    assert len(remaining) == 1
    assert remaining[0]["template_id"] == template_b_id
    assert remaining[0]["name"] == "Default"
    assert remaining[0]["data"] == {"bar": 1}


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


def test_get_asset_id_by_hash(tmp_path):
    db_path = tmp_path / "app.sqlite"

    store.upsert_asset(
        name="logo",
        kind="image",
        data=b"data",
        path=None,
        file_hash="asset-hash",
        width_px=10,
        height_px=10,
        dpi_x=203,
        dpi_y=203,
        db_path=db_path,
    )

    asset_id = store.get_asset_id_by_hash("asset-hash", db_path=db_path)
    assert isinstance(asset_id, int)
    assert asset_id > 0
    assert store.get_asset_id_by_hash("missing", db_path=db_path) is None


def test_raster_cache_round_trip(tmp_path):
    db_path = tmp_path / "app.sqlite"

    store.upsert_asset(
        name="logo",
        kind="image",
        data=b"data",
        path=None,
        file_hash="asset-hash",
        width_px=10,
        height_px=10,
        dpi_x=203,
        dpi_y=203,
        db_path=db_path,
    )

    asset_id = store.get_asset_id_by_hash("asset-hash", db_path=db_path)
    assert asset_id is not None

    cache_path = tmp_path / "cache.bin"
    cache_path.write_bytes(b"payload")

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

    with store.get_conn(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM raster_cache").fetchone()[0]
    assert count == 1

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
    assert (
        store.find_raster_cache(
            asset_id,
            160,
            80,
            (203, 203),
            "floyd",
            0.0,
            False,
            False,
            129,
            db_path=db_path,
        )
        is None
    )

    updated_path = tmp_path / "updated.bin"
    updated_path.write_bytes(b"payload2")
    stored_updated = store.insert_or_get_raster_cache(
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

    assert stored_updated == canonical_file_path(updated_path)

    with store.get_conn(db_path) as conn:
        count_after_update = conn.execute(
            "SELECT COUNT(*) FROM raster_cache"
        ).fetchone()[0]
    assert count_after_update == 1
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

def test_print_job_lifecycle(tmp_path):
    db_path = tmp_path / "app.sqlite"

    job_id = store.insert_print_job(
        payload_hash="hash-1",
        payload=b"payload",
        template_name="demo",
        template_backend="tspl",
        printer_name="printer-1",
        printer_backend="tspl",
        printer_transport="win32",
        media_settings={"media_type": "gap"},
        db_path=db_path,
    )

    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT status, pending_at, running_at, finished_at, failed_at, error_text"
            " FROM print_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["pending_at"] is not None
        assert row["running_at"] is None

    assert store.update_print_job_status(
        job_id=job_id, status="running", db_path=db_path
    )
    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT status, running_at FROM print_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "running"
        assert row["running_at"] is not None

    assert store.update_print_job_status(
        job_id=job_id, status="failed", error_text="boom", db_path=db_path
    )
    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT status, failed_at, error_text FROM print_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert row["failed_at"] is not None
        assert row["error_text"] == "boom"

    assert store.update_print_job_status(job_id=job_id, status="done", db_path=db_path)
    with store.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT status, finished_at, failed_at, error_text"
            " FROM print_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "done"
        assert row["finished_at"] is not None
        assert row["failed_at"] is None
        assert row["error_text"] is None

    payload = store.get_job_payload(job_id=job_id, db_path=db_path)
    assert payload == b"payload"
    payload_via_hash = store.get_job_payload(
        payload_hash="hash-1", db_path=db_path
    )
    assert payload_via_hash == b"payload"

def test_printer_profiles_crud(tmp_path):
    db_path = tmp_path / "app.sqlite"

    initial = {
        "media_gap_mm": "2.5",
        "media_mark_mm": None,
        "media_gap_offset_mm": "1.2",
        "media_mark_offset_mm": None,
        "media_fine_offset_mm": "",
        "media_calibrate_next": True,
        "media_speed": "6",
        "media_darkness": "10",
        "media_print_rate": "",
    }

    store.save_printer_profile("Zebra", initial, db_path=db_path)

    loaded = store.load_printer_profile("Zebra", db_path=db_path)
    assert loaded is not None
    assert loaded["media_gap_mm"] == 2.5
    assert loaded["media_mark_mm"] == 2.5
    assert loaded["media_gap_offset_mm"] == 1.2
    assert loaded["media_mark_offset_mm"] == 1.2
    assert loaded["media_fine_offset_mm"] == 0.0
    assert loaded["media_calibrate_next"] is True
    assert loaded["media_speed"] == 6
    assert "media_print_rate" not in loaded

    with store.get_conn(db_path) as conn:
        first_updated = conn.execute(
            "SELECT updated_at FROM printer_profiles WHERE name = ?",
            ("Zebra",),
        ).fetchone()[0]

    updated_settings = {
        "media_gap_offset_mm": 0,
        "media_mark_offset_mm": "3.4",
        "media_fine_offset_mm": 0.25,
        "media_calibrate_next": False,
        "media_speed": None,
        "media_darkness": 0,
    }

    store.save_printer_profile("Zebra", updated_settings, db_path=db_path)

    loaded_again = store.load_printer_profile("Zebra", db_path=db_path)
    assert loaded_again is not None
    assert loaded_again["media_gap_offset_mm"] == 0.0
    assert loaded_again["media_mark_offset_mm"] == 3.4
    assert loaded_again["media_fine_offset_mm"] == 0.25
    assert loaded_again["media_calibrate_next"] is False
    assert "media_speed" not in loaded_again
    assert "media_darkness" not in loaded_again

    with store.get_conn(db_path) as conn:
        second_updated = conn.execute(
            "SELECT updated_at FROM printer_profiles WHERE name = ?",
            ("Zebra",),
        ).fetchone()[0]

    assert second_updated != first_updated

    assert store.load_printer_profile("Missing", db_path=db_path) is None
