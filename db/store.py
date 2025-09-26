"""High level helpers for working with the application database."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from . import migrations

__all__ = ["get_conn", "init", "vacuum", "backup"]


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
