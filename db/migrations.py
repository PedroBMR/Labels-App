"""Database schema migrations for the Labels application."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Create or upgrade the database schema in ``conn``.

    The function is idempotent: if the schema is already at ``SCHEMA_VERSION``
    no work is performed.
    """

    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
    )
    has_meta = cursor.fetchone() is not None

    current_version: int | None = None
    if has_meta:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
        if row is not None:
            try:
                current_version = int(row[0])
            except (TypeError, ValueError):
                current_version = None

    def ensure_table(sql: str) -> None:
        conn.execute(sql)

    def has_column(table: str, column: str) -> bool:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    with conn:
        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                kind TEXT,
                path TEXT,
                file_hash TEXT,
                width_mm REAL,
                height_mm REAL,
                dpi INTEGER,
                tags TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name)
            )
            """
        )

        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT,
                file_hash TEXT,
                width_px INTEGER,
                height_px INTEGER,
                dpi_x REAL,
                dpi_y REAL,
                tags TEXT,
                data BLOB,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name)
            )
            """
        )

        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS raster_cache (
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
                path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    asset_id,
                    width_px,
                    height_px,
                    dpi_x,
                    dpi_y,
                    dither,
                    gamma,
                    sharpen,
                    invert,
                    threshold
                )
            )
            """
        )

        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                template_name TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )

        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS vars_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name)
            )
            """
        )

        ensure_table(
            """
            CREATE INDEX IF NOT EXISTS idx_assets_kind
            ON assets(kind)
            """
        )

        ensure_table(
            """
            CREATE INDEX IF NOT EXISTS idx_raster_cache_asset
            ON raster_cache(asset_id)
            """
        )

        ensure_table(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_print_jobs_created_at_id
            ON print_jobs(created_at, id)
            """
        )

        ensure_table(
            """
            CREATE INDEX IF NOT EXISTS idx_vars_presets_name
            ON vars_presets(name)
            """
        )

        if not has_column("templates", "path"):
            conn.execute("ALTER TABLE templates ADD COLUMN path TEXT")
        if not has_column("templates", "file_hash"):
            conn.execute("ALTER TABLE templates ADD COLUMN file_hash TEXT")
        if not has_column("templates", "kind"):
            conn.execute("ALTER TABLE templates ADD COLUMN kind TEXT")
        if not has_column("templates", "width_mm"):
            conn.execute("ALTER TABLE templates ADD COLUMN width_mm REAL")
        if not has_column("templates", "height_mm"):
            conn.execute("ALTER TABLE templates ADD COLUMN height_mm REAL")
        if not has_column("templates", "dpi"):
            conn.execute("ALTER TABLE templates ADD COLUMN dpi INTEGER")
        if not has_column("templates", "tags"):
            conn.execute("ALTER TABLE templates ADD COLUMN tags TEXT")

        if not has_column("assets", "kind"):
            conn.execute("ALTER TABLE assets ADD COLUMN kind TEXT")
            if has_column("assets", "type"):
                conn.execute("UPDATE assets SET kind = type WHERE kind IS NULL")
        if not has_column("assets", "path"):
            conn.execute("ALTER TABLE assets ADD COLUMN path TEXT")
        if not has_column("assets", "file_hash"):
            conn.execute("ALTER TABLE assets ADD COLUMN file_hash TEXT")
        if not has_column("assets", "width_px"):
            conn.execute("ALTER TABLE assets ADD COLUMN width_px INTEGER")
        if not has_column("assets", "height_px"):
            conn.execute("ALTER TABLE assets ADD COLUMN height_px INTEGER")
        if not has_column("assets", "dpi_x"):
            conn.execute("ALTER TABLE assets ADD COLUMN dpi_x REAL")
        if not has_column("assets", "dpi_y"):
            conn.execute("ALTER TABLE assets ADD COLUMN dpi_y REAL")
        if not has_column("assets", "tags"):
            conn.execute("ALTER TABLE assets ADD COLUMN tags TEXT")
        if not has_column("assets", "created_at"):
            conn.execute(
                "ALTER TABLE assets ADD COLUMN created_at TEXT NOT NULL"
                " DEFAULT CURRENT_TIMESTAMP"
            )
        if not has_column("assets", "updated_at"):
            conn.execute(
                "ALTER TABLE assets ADD COLUMN updated_at TEXT NOT NULL"
                " DEFAULT CURRENT_TIMESTAMP"
            )

        conn.execute(
            """
            INSERT INTO meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("schema_version", str(SCHEMA_VERSION)),
        )
