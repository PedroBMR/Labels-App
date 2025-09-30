"""Filesystem utilities for hashing and canonical paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["canonical_path", "file_hash"]


def canonical_path(path: str | Path) -> Path:
    """Return a normalised absolute path for ``path``.

    The function resolves symlinks when possible while tolerating missing files.
    """

    target = Path(path)
    try:
        return target.expanduser().resolve(strict=True)
    except FileNotFoundError:
        return target.expanduser().resolve(strict=False)


def file_hash(
    path: str | Path,
    *,
    algorithm: str = "sha256",
    chunk_size: int = 65536,
) -> str:
    """Return the hexadecimal hash for ``path`` using ``algorithm``.

    Args:
        path: File to hash.
        algorithm: Hash algorithm accepted by :mod:`hashlib`.
        chunk_size: Size of chunks read from disk.
    """

    target = Path(path)
    digest = hashlib.new(algorithm)
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
