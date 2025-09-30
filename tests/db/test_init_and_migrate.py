"""Tests for database initialization and migrations."""

from __future__ import annotations

import sys
from contextlib import closing
from types import ModuleType

if "PIL" not in sys.modules:
    pil_module = ModuleType("PIL")
    image_module = ModuleType("Image")
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module

from db import migrations, store

EXPECTED_TABLE_COLUMNS: dict[str, set[str]] = {
    "meta": {"key", "value"},
    "templates": {
        "id",
        "name",
        "data",
        "kind",
        "path",
        "file_hash",
        "width_mm",
        "height_mm",
        "dpi",
        "tags",
        "created_at",
        "updated_at",
    },
    "assets": {
        "id",
        "name",
        "kind",
        "path",
        "file_hash",
        "width_px",
        "height_px",
        "dpi_x",
        "dpi_y",
        "tags",
        "data",
        "created_at",
        "updated_at",
    },
    "printer_profiles": {
        "id",
        "name",
        "settings",
        "calibrate_next_print",
        "created_at",
        "updated_at",
        "media_type",
        "gap_mm",
        "offset_mm",
        "mark_mm",
        "darkness",
        "speed",
        "mark_offset_mm",
        "fine_offset_mm",
        "calibrate_next",
    },
    "raster_cache": {
        "id",
        "asset_id",
        "width_dots",
        "height_dots",
        "dpi_x",
        "dpi_y",
        "dither",
        "gamma",
        "sharpen",
        "invert",
        "threshold",
        "cache_path",
        "created_at",
    },
    "print_jobs": {
        "id",
        "created_at",
        "payload_hash",
        "payload",
        "template_name",
        "template_backend",
        "printer_name",
        "printer_backend",
        "printer_transport",
        "media_settings",
        "status",
        "pending_at",
        "running_at",
        "finished_at",
        "failed_at",
        "error_text",
    },
    "vars_presets": {
        "id",
        "template_id",
        "name",
        "data",
        "updated_at",
    },
}


def _get_table_names(conn) -> set[str]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cursor.fetchall()}


def _get_column_names(conn, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info('{table}')")
    return {row[1] for row in cursor.fetchall()}


def test_init_creates_expected_schema(tmp_path):
    db_path = tmp_path / "app.sqlite"
    store.configure_default_path(db_path)
    store.init(db_path)

    with closing(store.get_conn(db_path)) as conn:
        tables = _get_table_names(conn)
        for table, expected_columns in EXPECTED_TABLE_COLUMNS.items():
            assert table in tables
            columns = _get_column_names(conn, table)
            assert expected_columns <= columns

        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row is not None
        assert int(row[0]) == migrations.SCHEMA_VERSION

    store.init(db_path)

    with closing(store.get_conn(db_path)) as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row is not None
        assert int(row[0]) == migrations.SCHEMA_VERSION


def test_init_is_idempotent(tmp_path):
    db_path = tmp_path / "app.sqlite"
    store.configure_default_path(db_path)
    store.init(db_path)

    with closing(store.get_conn(db_path)) as conn:
        before = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert before is not None
        before_version = int(before[0])

    store.init(db_path)

    with closing(store.get_conn(db_path)) as conn:
        after = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert after is not None
        after_version = int(after[0])

    assert before_version == after_version == migrations.SCHEMA_VERSION
