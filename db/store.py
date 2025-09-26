"""High level helpers for working with the application database."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from . import migrations
from utils import recurso_caminho
from utils.fs import canonical_path as canonical_file_path

__all__ = [
    "backup",
    "configure_default_path",
    "default_db_path",
    "find_raster_cache",
    "get_conn",
    "get_asset_id_by_hash",
    "init",
    "insert_or_get_raster_cache",
    # upsert_asset(name, kind, data, path, file_hash, width_px, height_px,
    #              dpi_x, dpi_y, tags, updated_at, db_path)
    "upsert_asset",
    # upsert_template(name, data, path, file_hash, width_mm, height_mm,
    #                 dpi, tags, kind, updated_at, db_path)
    "upsert_template",
    "vacuum",
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


def find_raster_cache(
    asset_id: int,
    width_px: int,
    height_px: int,
    dpi: tuple[int, int],
    dither: str,
    gamma: float | int | None,
    sharpen: bool,
    invert: bool,
    threshold: int,
    *,
    db_path: str | Path | None = None,
) -> Path | None:
    """Return the cached raster path matching the provided parameters."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    gamma_value = _normalise_gamma(gamma)
    params = (
        asset_id,
        int(width_px),
        int(height_px),
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
            SELECT path
            FROM raster_cache
            WHERE asset_id = ?
              AND width_px = ?
              AND height_px = ?
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
    return Path(row["path"])


def insert_or_get_raster_cache(
    *,
    asset_id: int,
    width_px: int,
    height_px: int,
    dpi: tuple[int, int],
    dither: str,
    gamma: float | int | None,
    sharpen: bool,
    invert: bool,
    threshold: int,
    path: str | Path,
    db_path: str | Path | None = None,
) -> Path:
    """Insert or update a raster cache entry and return its path."""

    database = _resolve_db_path(db_path)
    _ensure_initialised(database)

    gamma_value = _normalise_gamma(gamma)
    sharpen_value = int(bool(sharpen))
    invert_value = int(bool(invert))
    threshold_value = int(threshold)
    resolved_path = canonical_file_path(path)

    params = (
        asset_id,
        int(width_px),
        int(height_px),
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
                    width_px,
                    height_px,
                    dpi_x,
                    dpi_y,
                    dither,
                    gamma,
                    sharpen,
                    invert,
                    threshold,
                    path
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
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
                ) DO UPDATE SET path = excluded.path
                """,
                params,
            )

    return resolved_path
