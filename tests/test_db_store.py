from __future__ import annotations

from db import migrations, store


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
