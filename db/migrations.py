"""Database schema migrations for the Labels application."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1


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

    if current_version == SCHEMA_VERSION:
        return

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                data BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raster_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                dpi INTEGER NOT NULL,
                payload BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(fingerprint)
            )
            """
        )

        conn.execute(
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

        conn.execute(
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

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assets_type
            ON assets(type)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raster_cache_template
            ON raster_cache(template_name)
            """
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_print_jobs_created_at_id
            ON print_jobs(created_at, id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vars_presets_name
            ON vars_presets(name)
            """
        )

        conn.execute(
            """
            INSERT INTO meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("schema_version", str(SCHEMA_VERSION)),
        )
