"""Database schema migrations for the Labels application."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import sqlite3


def _migration_1(conn: sqlite3.Connection) -> None:
    def ensure_table(sql: str) -> None:
        conn.execute(sql)

    def table_exists(name: str) -> bool:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return cursor.fetchone() is not None

    def table_columns(name: str) -> set[str]:
        cursor = conn.execute(f"PRAGMA table_info({name})")
        return {row[1] for row in cursor.fetchall()}

    def has_column(table: str, column: str) -> bool:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

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
        CREATE TABLE IF NOT EXISTS printer_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            settings TEXT NOT NULL,
            calibrate_next_print INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name)
        )
        """
    )

    if table_exists("raster_cache"):
        columns = table_columns("raster_cache")
        legacy_markers = {"width_px", "height_px", "path"}
        expected_columns = {
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
        }
        if legacy_markers & columns or not expected_columns <= columns:
            conn.execute("DROP TABLE raster_cache")

    ensure_table(
        """
        CREATE TABLE IF NOT EXISTS raster_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            width_dots INTEGER NOT NULL,
            height_dots INTEGER NOT NULL,
            dpi_x INTEGER NOT NULL,
            dpi_y INTEGER NOT NULL,
            dither TEXT NOT NULL,
            gamma REAL NOT NULL DEFAULT 0,
            sharpen INTEGER NOT NULL,
            invert INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            cache_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(
                asset_id,
                width_dots,
                height_dots,
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

    create_print_jobs_sql = """
        CREATE TABLE IF NOT EXISTS print_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload_hash TEXT,
            payload BLOB,
            template_name TEXT,
            template_backend TEXT,
            printer_name TEXT,
            printer_backend TEXT,
            printer_transport TEXT,
            media_settings TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            pending_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            running_at TEXT,
            finished_at TEXT,
            failed_at TEXT,
            error_text TEXT
        )
    """

    expected_print_job_columns = {
        "payload_hash",
        "payload",
        "template_backend",
        "printer_name",
        "printer_backend",
        "printer_transport",
        "media_settings",
        "pending_at",
        "running_at",
        "finished_at",
        "failed_at",
        "error_text",
    }

    if table_exists("print_jobs"):
        print_job_columns = table_columns("print_jobs")
        needs_upgrade = not expected_print_job_columns <= print_job_columns
    else:
        print_job_columns = set()
        needs_upgrade = True

    if needs_upgrade and table_exists("print_jobs"):
        conn.execute("DROP INDEX IF EXISTS idx_print_jobs_created_at_id")
        conn.execute("ALTER TABLE print_jobs RENAME TO print_jobs_legacy")
        conn.execute(create_print_jobs_sql)

        cursor = conn.execute(
            "SELECT id, created_at, template_name, payload, status FROM print_jobs_legacy"
        )
        for row in cursor.fetchall():
            legacy_id, created_at, template_name, payload_value, status = row
            if isinstance(payload_value, memoryview):
                payload_bytes = bytes(payload_value)
            elif isinstance(payload_value, bytes):
                payload_bytes = payload_value
            elif payload_value is None:
                payload_bytes = None
            else:
                payload_bytes = str(payload_value).encode("utf-8", errors="ignore")

            payload_hash = (
                hashlib.sha256(payload_bytes).hexdigest()
                if payload_bytes is not None
                else None
            )
            conn.execute(
                """
                INSERT INTO print_jobs(
                    id,
                    created_at,
                    payload_hash,
                    payload,
                    template_name,
                    status,
                    pending_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy_id,
                    created_at,
                    payload_hash,
                    payload_bytes,
                    template_name,
                    status,
                    created_at,
                ),
            )

        conn.execute("DROP TABLE print_jobs_legacy")
    else:
        ensure_table(create_print_jobs_sql)

    def create_vars_presets_schema() -> None:
        ensure_table(
            """
            CREATE TABLE IF NOT EXISTS vars_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE CASCADE
            )
            """
        )
        ensure_table(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_vars_presets_template_name
            ON vars_presets(template_id, name)
            """
        )
        ensure_table(
            """
            CREATE INDEX IF NOT EXISTS idx_vars_presets_template
            ON vars_presets(template_id)
            """
        )

    if table_exists("vars_presets"):
        vars_preset_columns = table_columns("vars_presets")
        if "template_id" not in vars_preset_columns:
            conn.execute("ALTER TABLE vars_presets RENAME TO vars_presets_legacy")
            create_vars_presets_schema()

            template_rows = conn.execute(
                "SELECT id, name FROM templates"
            ).fetchall()
            template_by_name = {row[1]: row[0] for row in template_rows}
            fallback_template_id = None
            if len(template_rows) == 1:
                fallback_template_id = template_rows[0][0]

            legacy_rows = conn.execute(
                "SELECT id, name, data, updated_at FROM vars_presets_legacy"
            ).fetchall()

            def resolve_template_id(data_value: str) -> int | None:
                if not data_value:
                    return None
                try:
                    payload = json.loads(data_value)
                except (TypeError, ValueError, json.JSONDecodeError):
                    return None

                template_name: str | None = None
                if isinstance(payload, dict):
                    template_id_value = payload.get("template_id")
                    if isinstance(template_id_value, int):
                        return template_id_value

                    name_keys = (
                        "template_name",
                        "templateName",
                        "template",
                    )
                    for key in name_keys:
                        value = payload.get(key)
                        if isinstance(value, str):
                            template_name = value
                            break
                        if isinstance(value, dict):
                            nested_name = value.get("name")
                            if isinstance(nested_name, str):
                                template_name = nested_name
                                break

                    if template_name is None and "meta" in payload:
                        meta = payload.get("meta")
                        if isinstance(meta, dict):
                            for key in name_keys:
                                value = meta.get(key)
                                if isinstance(value, str):
                                    template_name = value
                                    break
                                if isinstance(value, dict):
                                    nested_name = value.get("name")
                                    if isinstance(nested_name, str):
                                        template_name = nested_name
                                        break

                if template_name is not None:
                    return template_by_name.get(template_name)

                return None

            for row in legacy_rows:
                row_id, name, data_value, updated_at = row
                template_id = resolve_template_id(data_value)
                if template_id is None:
                    if fallback_template_id is not None:
                        template_id = fallback_template_id
                    else:
                        raise RuntimeError(
                            "Unable to determine template for vars preset"
                            f" '{name}' during migration"
                        )

                conn.execute(
                    """
                    INSERT INTO vars_presets(
                        id, template_id, name, data, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (row_id, template_id, name, data_value, updated_at),
                )

            conn.execute("DROP TABLE vars_presets_legacy")
        else:
            create_vars_presets_schema()
    else:
        create_vars_presets_schema()

    conn.execute("DROP INDEX IF EXISTS idx_vars_presets_name")

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
        CREATE INDEX IF NOT EXISTS idx_print_jobs_status_created
        ON print_jobs(status, created_at)
        """
    )
    ensure_table(
        """
        CREATE INDEX IF NOT EXISTS idx_print_jobs_payload_hash
        ON print_jobs(payload_hash)
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

    if table_exists("printer_profiles"):
        if not has_column("printer_profiles", "media_type"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN media_type TEXT")
        if not has_column("printer_profiles", "gap_mm"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN gap_mm REAL")
        if not has_column("printer_profiles", "offset_mm"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN offset_mm REAL")
        if not has_column("printer_profiles", "mark_mm"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN mark_mm REAL")
        if not has_column("printer_profiles", "darkness"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN darkness INTEGER")
        if not has_column("printer_profiles", "speed"):
            conn.execute("ALTER TABLE printer_profiles ADD COLUMN speed INTEGER")
        if not has_column("printer_profiles", "mark_offset_mm"):
            conn.execute(
                "ALTER TABLE printer_profiles ADD COLUMN mark_offset_mm REAL"
            )
        if not has_column("printer_profiles", "fine_offset_mm"):
            conn.execute(
                "ALTER TABLE printer_profiles ADD COLUMN fine_offset_mm REAL"
            )
        if not has_column("printer_profiles", "calibrate_next"):
            conn.execute(
                "ALTER TABLE printer_profiles ADD COLUMN calibrate_next INTEGER"
                " NOT NULL DEFAULT 0"
            )
        if not has_column("printer_profiles", "updated_at"):
            conn.execute(
                "ALTER TABLE printer_profiles ADD COLUMN updated_at TEXT NOT NULL"
                " DEFAULT CURRENT_TIMESTAMP"
            )


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_migration_1]

SCHEMA_VERSION = len(MIGRATIONS)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Create or upgrade the database schema in ``conn``."""

    conn.execute("PRAGMA foreign_keys = ON")

    current_version = 0
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", ("schema_version",)
        ).fetchone()
    except sqlite3.DatabaseError:
        row = None

    if row is not None:
        try:
            current_version = int(row[0])
        except (TypeError, ValueError):
            current_version = 0
        else:
            if current_version < 0:
                current_version = 0

    if current_version >= SCHEMA_VERSION:
        return

    with conn:
        for version in range(current_version + 1, SCHEMA_VERSION + 1):
            migration = MIGRATIONS[version - 1]
            migration(conn)

        conn.execute(
            """
            INSERT INTO meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("schema_version", str(SCHEMA_VERSION)),
        )
