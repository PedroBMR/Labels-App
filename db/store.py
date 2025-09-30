"""High level helpers for working with the application database."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence

from utils import recurso_caminho
from utils.fs import canonical_path as canonical_file_path

from . import migrations

__all__ = [
    "backup",
    "configure_default_path",
    "default_db_path",
    "delete_vars_preset",
    "get_conn",
    "get_template_id_by_name",
    "init",
    "get_asset_id_by_hash",
    "find_raster_cache",
    "insert_or_get_raster_cache",
    "insert_print_job",
    "list_print_jobs",
    "list_vars_presets",
    "get_print_job",
    "load_printer_profile",
    "save_printer_profile",
    # upsert_asset(name, kind, data, path, file_hash, width_px, height_px,
    #              dpi_x, dpi_y, tags, updated_at, db_path)
    "upsert_asset",
    # upsert_template(name, data, path, file_hash, width_mm, height_mm,
    #                 dpi, tags, kind, updated_at, db_path)
    "upsert_template",
    "load_vars_preset",
    "save_vars_preset",
    "update_print_job_status",
    "get_job_payload",
    "vacuum",
    "integrity_check",
]

DEFAULT_DB_FILENAME = "app.sqlite"

_DEFAULT_DB_PATH: Path | None = None
_INITIALISED: set[Path] = set()


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """Return a connection to ``db_path``."""

    path = str(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: str | Path) -> None:
    """Initialise the database located at ``db_path``."""

    with contextlib.closing(get_conn(db_path)) as conn:
        migrations.apply_migrations(conn)


def default_db_path() -> Path:
    """Return the default database path creating parent directories as needed."""

    global _DEFAULT_DB_PATH
    if _DEFAULT_DB_PATH is not None:
        return _DEFAULT_DB_PATH

    env_override = os.environ.get("LABELS_DB_PATH")
    if env_override:
        path = Path(env_override)
    else:
        data_root = Path(recurso_caminho("_data"))
        data_root.mkdir(parents=True, exist_ok=True)
        path = data_root / DEFAULT_DB_FILENAME
    path = canonical_file_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _DEFAULT_DB_PATH = path
    return path


def configure_default_path(path: str | Path) -> None:
    """Override the default database path used by store helpers."""

    global _DEFAULT_DB_PATH
    resolved = canonical_file_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _DEFAULT_DB_PATH = resolved
    _INITIALISED.discard(resolved)


def vacuum(db_path: str | Path) -> None:
    """Vacuum the database file located at ``db_path``."""

    with contextlib.closing(get_conn(db_path)) as conn:
        conn.execute("VACUUM")


def backup(db_path: str | Path, out_path: str | Path) -> None:
    """Create a backup of ``db_path`` at ``out_path``."""

    with contextlib.closing(get_conn(db_path)) as src, contextlib.closing(
        sqlite3.connect(str(out_path))
    ) as dest:
        src.backup(dest)
        dest.commit()


def integrity_check(
    target: sqlite3.Connection | str | Path | None = None,
) -> bool:
    """Return ``True`` if the database passes SQLite's integrity check."""

    if isinstance(target, sqlite3.Connection):
        return _integrity_check_conn(target)

    path = _resolve_db_path(target)
    with contextlib.closing(get_conn(path)) as conn:
        return _integrity_check_conn(conn)


def _integrity_check_conn(conn: sqlite3.Connection) -> bool:
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError:
        return False
    return len(rows) == 1 and rows[0][0] == "ok"


def _resolve_db_path(db_path: str | Path | None) -> Path:
    if db_path is None:
        return default_db_path()
    resolved = canonical_file_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _ensure_initialised(db_path: Path) -> None:
    if db_path in _INITIALISED:
        return
    init(db_path)
    _INITIALISED.add(db_path)


def _normalise_gamma(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value) if float(value) > 0 else 0.0


def _serialise_json(data: Mapping[str, object] | Sequence[object] | str) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _coerce_media_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if number == 0:
        return 0.0
    return number


def _coerce_optional_int(value: object) -> int | None:
    if value in (None, "", False):
        return None
    try:
        number = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalise_printer_settings(settings: Mapping[str, object]) -> dict[str, object]:
    payload = dict(settings)

    gap_mm = _coerce_media_float(payload.get("media_gap_mm"), 0.0)
    mark_mm = _coerce_media_float(payload.get("media_mark_mm"), gap_mm)
    payload["media_gap_mm"] = gap_mm
    payload["media_mark_mm"] = mark_mm

    gap_offset = _coerce_media_float(payload.get("media_gap_offset_mm"), 0.0)
    mark_offset = _coerce_media_float(
        payload.get("media_mark_offset_mm"), gap_offset
    )
    fine_offset = _coerce_media_float(payload.get("media_fine_offset_mm"), 0.0)

    payload["media_gap_offset_mm"] = gap_offset
    payload["media_mark_offset_mm"] = mark_offset
    payload["media_fine_offset_mm"] = fine_offset

    calibrate = bool(payload.get("media_calibrate_next"))
    payload["media_calibrate_next"] = calibrate

    speed = _coerce_optional_int(payload.get("media_speed"))
    if speed is None:
        payload.pop("media_speed", None)
    else:
        payload["media_speed"] = speed

    darkness = _coerce_optional_int(
        payload.get("media_darkness", payload.get("darkness"))
    )
    if darkness is None:
        payload.pop("media_darkness", None)
    else:
        payload["media_darkness"] = darkness

    print_rate = payload.get("media_print_rate")
    if print_rate in (None, "", 0, 0.0):
        payload.pop("media_print_rate", None)

    return payload


def get_template_id_by_name(
    name: str, *, db_path: str | Path | None = None
) -> int | None:
    """Return the template identifier for ``name`` or ``None`` if it does not exist."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            "SELECT id FROM templates WHERE name = ?",
            (name,),
        ).fetchone()

    if row is None:
        return None
    return int(row[0])


def load_printer_profile(
    name: str, *, db_path: str | Path | None = None
) -> dict[str, object] | None:
    """Load normalised printer settings for ``name`` if it exists."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            "SELECT settings, calibrate_next_print "
            "FROM printer_profiles WHERE name = ?",
            (name,),
        ).fetchone()

    if row is None:
        return None

    raw_settings = row["settings"]
    payload: dict[str, object]
    if isinstance(raw_settings, str):
        try:
            loaded = json.loads(raw_settings)
        except (TypeError, ValueError, json.JSONDecodeError):
            loaded = {}
    else:
        loaded = {}

    if isinstance(loaded, dict):
        payload = dict(loaded)
    else:
        payload = {}

    gap_mm = _coerce_media_float(payload.get("media_gap_mm"), 0.0)
    mark_mm = _coerce_media_float(payload.get("media_mark_mm"), gap_mm)
    payload["media_gap_mm"] = gap_mm
    payload["media_mark_mm"] = mark_mm

    gap_offset = _coerce_media_float(payload.get("media_gap_offset_mm"), 0.0)
    mark_offset = _coerce_media_float(
        payload.get("media_mark_offset_mm"), gap_offset
    )
    fine_offset = _coerce_media_float(payload.get("media_fine_offset_mm"), 0.0)

    payload["media_gap_offset_mm"] = gap_offset
    payload["media_mark_offset_mm"] = mark_offset
    payload["media_fine_offset_mm"] = fine_offset

    calibrate = bool(payload.get("media_calibrate_next")) or bool(
        row["calibrate_next_print"]
    )
    payload["media_calibrate_next"] = calibrate

    speed = _coerce_optional_int(payload.get("media_speed"))
    if speed is not None:
        payload["media_speed"] = speed
    elif "media_speed" in payload:
        payload.pop("media_speed")

    darkness = _coerce_optional_int(
        payload.get("media_darkness", payload.get("darkness"))
    )
    if darkness is not None:
        payload["media_darkness"] = darkness
    elif "media_darkness" in payload:
        payload.pop("media_darkness")

    payload.pop("darkness", None)

    print_rate = payload.get("media_print_rate")
    if print_rate in (None, "", 0, 0.0):
        payload.pop("media_print_rate", None)

    return payload


def save_printer_profile(
    name: str,
    settings: Mapping[str, object],
    *,
    db_path: str | Path | None = None,
) -> None:
    """Persist ``settings`` for ``name`` inserting or updating as needed."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    existing_settings: dict[str, object] = {}

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            "SELECT settings FROM printer_profiles WHERE name = ?",
            (name,),
        ).fetchone()

    if row is not None:
        raw_settings = row["settings"]
        loaded: object
        if isinstance(raw_settings, str):
            try:
                loaded = json.loads(raw_settings)
            except (TypeError, ValueError, json.JSONDecodeError):
                loaded = {}
        else:
            loaded = {}

        if isinstance(loaded, dict):
            existing_settings = dict(loaded)

    merged_settings: dict[str, object] = dict(existing_settings)
    merged_settings.update(settings)

    normalised = _normalise_printer_settings(merged_settings)
    calibrate = bool(normalised.get("media_calibrate_next"))
    payload = _serialise_json(normalised)
    timestamp = datetime.now(UTC).isoformat()

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO printer_profiles(
                    name,
                    settings,
                    calibrate_next_print,
                    updated_at
                )
                VALUES(?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    settings = excluded.settings,
                    calibrate_next_print = excluded.calibrate_next_print,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    payload,
                    int(calibrate),
                    timestamp,
                ),
            )

def upsert_template(
    *,
    name: str,
    data: str,
    path: str | Path | None,
    file_hash: str,
    width_mm: float | None,
    height_mm: float | None,
    dpi: int | None,
    kind: str | None = None,
    tags: Sequence[str] | None = None,
    updated_at: datetime | str | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Insert or update a template record in the database."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    timestamp: str
    if isinstance(updated_at, str):
        timestamp = updated_at
    elif isinstance(updated_at, datetime):
        timestamp = updated_at.astimezone(UTC).isoformat()
    else:
        timestamp = datetime.now(UTC).isoformat()

    payload = json.dumps(list(tags)) if tags else None
    path_value = (
        str(canonical_file_path(path)) if path is not None else None
    )
    kind_value = str(kind) if kind is not None else None

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO templates(
                    name,
                    data,
                    kind,
                    path,
                    file_hash,
                    width_mm,
                    height_mm,
                    dpi,
                    tags,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    data = excluded.data,
                    kind = excluded.kind,
                    path = excluded.path,
                    file_hash = excluded.file_hash,
                    width_mm = excluded.width_mm,
                    height_mm = excluded.height_mm,
                    dpi = excluded.dpi,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    data,
                    kind_value,
                    path_value,
                    file_hash,
                    width_mm,
                    height_mm,
                    dpi,
                    payload,
                    timestamp,
                ),
            )


def upsert_asset(
    *,
    name: str,
    kind: str,
    data: bytes | memoryview | None,
    path: str | Path | None,
    file_hash: str | None,
    width_px: int | None,
    height_px: int | None,
    dpi_x: float | int | None,
    dpi_y: float | int | None,
    tags: Sequence[str] | None = None,
    updated_at: datetime | str | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Insert or update an asset record in the database."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    timestamp: str
    if isinstance(updated_at, str):
        timestamp = updated_at
    elif isinstance(updated_at, datetime):
        timestamp = updated_at.astimezone(UTC).isoformat()
    else:
        timestamp = datetime.now(UTC).isoformat()

    payload = json.dumps(list(tags)) if tags else None
    path_value = (
        str(canonical_file_path(path)) if path is not None else None
    )
    data_value: bytes | None
    if data is None:
        data_value = None
    elif isinstance(data, (bytes, bytearray)):
        data_value = bytes(data)
    else:
        data_value = bytes(memoryview(data))

    def _to_float(value: float | int | None) -> float | None:
        if value is None:
            return None
        return float(value)

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO assets(
                    name,
                    kind,
                    data,
                    path,
                    file_hash,
                    width_px,
                    height_px,
                    dpi_x,
                    dpi_y,
                    tags,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    kind = excluded.kind,
                    data = excluded.data,
                    path = excluded.path,
                    file_hash = excluded.file_hash,
                    width_px = excluded.width_px,
                    height_px = excluded.height_px,
                    dpi_x = excluded.dpi_x,
                    dpi_y = excluded.dpi_y,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    kind,
                    data_value,
                    path_value,
                    file_hash,
                    width_px,
                    height_px,
                    _to_float(dpi_x),
                    _to_float(dpi_y),
                    payload,
                    timestamp,
                ),
            )


def get_asset_id_by_hash(
    file_hash: str,
    *,
    db_path: str | Path | None = None,
) -> int | None:
    """Return the asset identifier for ``file_hash`` if present."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            "SELECT id FROM assets WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])


def save_vars_preset(
    *,
    template_id: int,
    name: str,
    data: Mapping[str, object] | Sequence[object] | str,
    updated_at: datetime | str | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Create or update a variables preset for the given template."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    if isinstance(updated_at, str):
        timestamp = updated_at
    elif isinstance(updated_at, datetime):
        timestamp = updated_at.astimezone(UTC).isoformat()
    else:
        timestamp = datetime.now(UTC).isoformat()

    payload = _serialise_json(data)

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO vars_presets(template_id, name, data, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(template_id, name) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (template_id, name, payload, timestamp),
            )


def load_vars_preset(
    *,
    template_id: int,
    name: str,
    db_path: str | Path | None = None,
) -> Mapping[str, object] | Sequence[object] | None:
    """Load a variables preset for ``template_id`` and ``name``."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            """
            SELECT data FROM vars_presets
            WHERE template_id = ? AND name = ?
            """,
            (template_id, name),
        ).fetchone()

    if row is None:
        return None

    try:
        return json.loads(row[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def list_vars_presets(
    *,
    template_id: int | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    """Return variables presets optionally filtered by ``template_id``."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    query = "SELECT id, template_id, name, data, updated_at FROM vars_presets"
    params: tuple[object, ...]
    if template_id is not None:
        query += " WHERE template_id = ?"
        params = (template_id,)
    else:
        params = ()
    query += " ORDER BY name, id"

    with contextlib.closing(get_conn(database)) as conn:
        rows = conn.execute(query, params).fetchall()

    presets: list[dict[str, object]] = []
    for row in rows:
        try:
            decoded = json.loads(row["data"])
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        presets.append(
            {
                "id": row["id"],
                "template_id": row["template_id"],
                "name": row["name"],
                "data": decoded,
                "updated_at": row["updated_at"],
            }
        )
    return presets


def delete_vars_preset(
    *,
    template_id: int,
    name: str,
    db_path: str | Path | None = None,
) -> bool:
    """Delete a variables preset returning ``True`` if it existed."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            cursor = conn.execute(
                "DELETE FROM vars_presets WHERE template_id = ? AND name = ?",
                (template_id, name),
            )
    return cursor.rowcount > 0


def find_raster_cache(
    asset_id: int,
    width_dots: int,
    height_dots: int,
    dpi: tuple[int, int],
    dither: str,
    gamma: float | int | None,
    sharpen: bool,
    invert: bool,
    threshold: int,
    *,
    db_path: str | Path | None = None,
) -> Path | None:
    """Return the cached raster path matching the provided parameters.

    The arguments are a thin abstraction over the ``raster_cache`` table and map
    directly to the corresponding columns.  Callers such as
    :mod:`imaging.raster` should use this helper instead of issuing SQL queries
    directly so that schema changes remain encapsulated in this module.
    """

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    gamma_value = _normalise_gamma(gamma)
    params = (
        asset_id,
        int(width_dots),
        int(height_dots),
        int(dpi[0]),
        int(dpi[1]),
        dither,
        gamma_value,
        int(bool(sharpen)),
        int(bool(invert)),
        int(threshold),
    )

    with contextlib.closing(get_conn(database)) as conn:
        row = conn.execute(
            """
            SELECT cache_path
            FROM raster_cache
            WHERE asset_id = ?
              AND width_dots = ?
              AND height_dots = ?
              AND dpi_x = ?
              AND dpi_y = ?
              AND dither = ?
              AND gamma = ?
              AND sharpen = ?
              AND invert = ?
              AND threshold = ?
            """,
            params,
        ).fetchone()

    if row is None:
        return None
    return Path(row["cache_path"])


def insert_or_get_raster_cache(
    *,
    asset_id: int,
    width_dots: int,
    height_dots: int,
    dpi: tuple[int, int],
    dither: str,
    gamma: float | int | None,
    sharpen: bool,
    invert: bool,
    threshold: int,
    cache_path: str | Path,
    db_path: str | Path | None = None,
) -> Path:
    """Insert or update a raster cache entry and return its canonical path.

    The record is uniquely identified by the rendering parameters and the
    resulting ``cache_path`` is stored using
    :func:`utils.fs.canonical_path`.  Repeated invocations with the same
    parameters update the cache path while keeping a single database row.
    """

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    gamma_value = _normalise_gamma(gamma)
    sharpen_value = int(bool(sharpen))
    invert_value = int(bool(invert))
    threshold_value = int(threshold)
    resolved_path = canonical_file_path(cache_path)

    params = (
        asset_id,
        int(width_dots),
        int(height_dots),
        int(dpi[0]),
        int(dpi[1]),
        dither,
        gamma_value,
        sharpen_value,
        invert_value,
        threshold_value,
        str(resolved_path),
    )

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO raster_cache(
                    asset_id,
                    width_dots,
                    height_dots,
                    dpi_x,
                    dpi_y,
                    dither,
                    gamma,
                    sharpen,
                    invert,
                    threshold,
                    cache_path
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
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
                ) DO UPDATE SET cache_path = excluded.cache_path
                """,
                params,
            )

    return resolved_path


def insert_print_job(
    *,
    payload_hash: str,
    payload: bytes | memoryview,
    template_name: str | None = None,
    template_backend: str | None = None,
    printer_name: str | None = None,
    printer_backend: str | None = None,
    printer_transport: str | None = None,
    printer_host: str | None = None,
    printer_port: int | None = None,
    media_settings: Mapping[str, object] | None = None,
    db_path: str | Path | None = None,
) -> int:
    """Insert a new print job row returning its identifier."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    pending_at = datetime.now(UTC).isoformat()
    media_blob = (
        json.dumps(media_settings, ensure_ascii=False, sort_keys=True)
        if media_settings
        else None
    )

    payload_bytes = bytes(payload)

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO print_jobs(
                    payload_hash,
                    payload,
                    template_name,
                    template_backend,
                    printer_name,
                    printer_backend,
                    printer_transport,
                    printer_host,
                    printer_port,
                    media_settings,
                    status,
                    pending_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    payload_hash,
                    sqlite3.Binary(payload_bytes),
                    template_name,
                    template_backend,
                    printer_name,
                    printer_backend,
                    printer_transport,
                    printer_host,
                    printer_port,
                    media_blob,
                    pending_at,
                ),
            )
            job_id = int(cursor.lastrowid)
    return job_id


def update_print_job_status(
    *,
    status: str,
    job_id: int | None = None,
    payload_hash: str | None = None,
    error_text: str | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Update ``status`` for the job identified by ``job_id`` or ``payload_hash``."""

    if job_id is None and payload_hash is None:
        raise ValueError("job_id or payload_hash must be provided")

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    status_value = status.lower()
    timestamp_columns = {
        "pending": "pending_at",
        "running": "running_at",
        "done": "finished_at",
        "failed": "failed_at",
    }
    column = timestamp_columns.get(status_value)
    timestamp = datetime.now(UTC).isoformat()

    assignments: list[str] = ["status = ?"]
    params: list[object] = [status_value]

    if column is not None:
        assignments.append(f"{column} = ?")
        params.append(timestamp)

    if status_value == "failed":
        assignments.append("error_text = ?")
        params.append(error_text or "")
        assignments.append("finished_at = NULL")
    elif status_value == "done":
        assignments.append("error_text = NULL")
        assignments.append("failed_at = NULL")
    elif status_value == "running":
        assignments.append("error_text = NULL")
        assignments.append("failed_at = NULL")

    filters: list[str] = []
    if job_id is not None:
        filters.append("id = ?")
        params.append(job_id)
    if payload_hash is not None:
        filters.append("payload_hash = ?")
        params.append(payload_hash)

    where_clause = " AND ".join(filters)

    with contextlib.closing(get_conn(database)) as conn:
        with conn:
            cursor = conn.execute(
                f"UPDATE print_jobs SET {', '.join(assignments)} WHERE {where_clause}",
                params,
            )
            return cursor.rowcount > 0


def get_job_payload(
    *,
    job_id: int | None = None,
    payload_hash: str | None = None,
    db_path: str | Path | None = None,
) -> bytes | None:
    """Fetch the payload associated with ``job_id`` or ``payload_hash``."""

    if job_id is None and payload_hash is None:
        raise ValueError("job_id or payload_hash must be provided")

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    filters: list[str] = []
    params: list[object] = []
    if job_id is not None:
        filters.append("id = ?")
        params.append(job_id)
    if payload_hash is not None:
        filters.append("payload_hash = ?")
        params.append(payload_hash)

    where_clause = " AND ".join(filters)

    with contextlib.closing(get_conn(database)) as conn:
        cursor = conn.execute(
            "SELECT payload FROM print_jobs "
            f"WHERE {where_clause} ORDER BY id DESC LIMIT 1",
            params,
        )
        row = cursor.fetchone()
    if row is None:
        return None
    payload_value = row[0]
    if payload_value is None:
        return None
    if isinstance(payload_value, memoryview):
        return bytes(payload_value)
    return bytes(payload_value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def get_print_job(
    *, job_id: int, db_path: str | Path | None = None
) -> dict[str, object] | None:
    """Return the print job record identified by ``job_id``."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    with contextlib.closing(get_conn(database)) as conn:
        cursor = conn.execute(
            """
            SELECT
                id,
                created_at,
                payload_hash,
                template_name,
                template_backend,
                printer_name,
                printer_backend,
                printer_transport,
                printer_host,
                printer_port,
                media_settings,
                status,
                pending_at,
                running_at,
                finished_at,
                failed_at,
                error_text
            FROM print_jobs
            WHERE id = ?
            LIMIT 1
            """,
            (job_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_print_jobs(
    *,
    limit: int = 50,
    offset: int = 0,
    status: Sequence[str] | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    """Return recent print jobs ordered from newest to oldest."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    filters: list[str] = []
    params: list[object] = []
    if status:
        placeholders = ", ".join("?" for _ in status)
        filters.append(f"status IN ({placeholders})")
        params.extend(str(value).lower() for value in status)

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    query = f"""
        SELECT
            id,
            created_at,
            payload_hash,
            template_name,
            template_backend,
            printer_name,
            printer_backend,
            printer_transport,
            printer_host,
            printer_port,
            media_settings,
            status,
            pending_at,
            running_at,
            finished_at,
            failed_at,
            error_text
        FROM print_jobs
        {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
    """

    params.extend([int(limit), int(offset)])

    with contextlib.closing(get_conn(database)) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    return [_row_to_dict(row) for row in rows]
