"""Helpers for loading images while indexing assets in the database."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from PIL import Image

from utils.fs import canonical_path, file_hash

__all__ = ["load_image"]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from db import store as db_store_module


def _guess_kind(name: str | None, image: Image.Image) -> str:
    if name:
        suffix = Path(name).suffix.lower()
        if suffix:
            return suffix.lstrip(".")
    fmt = getattr(image, "format", None)
    if isinstance(fmt, str) and fmt.strip():
        return fmt.lower()
    return "image"


def _extract_dpi(image: Image.Image) -> tuple[float | None, float | None]:
    dpi = image.info.get("dpi")
    if isinstance(dpi, (tuple, list)) and len(dpi) >= 2:
        try:
            return float(dpi[0]), float(dpi[1])
        except (TypeError, ValueError):
            pass
    resolution = image.info.get("resolution")
    if isinstance(resolution, (tuple, list)) and len(resolution) >= 2:
        try:
            return float(resolution[0]), float(resolution[1])
        except (TypeError, ValueError):
            pass
    return None, None


def _derive_name(name: str | None, kind: str) -> str:
    if name:
        return name
    return f"memory:{kind}:{uuid.uuid4().hex}"


def _record_asset(
    image: Image.Image,
    *,
    name: str | None,
    path: str | Path | None,
    data: bytes | memoryview | None,
) -> None:
    width, height = image.size
    dpi_x, dpi_y = _extract_dpi(image)
    canonical = canonical_path(path) if path is not None else None
    kind = _guess_kind(name or (canonical.name if canonical else None), image)
    asset_name = _derive_name(name or (canonical.name if canonical else None), kind)
    if canonical is not None:
        try:
            digest = file_hash(canonical)
        except FileNotFoundError:
            digest = None
    else:
        digest = None
    from db import store as db_store

    db_store.upsert_asset(
        name=asset_name,
        kind=kind,
        data=data,
        path=str(canonical) if canonical is not None else None,
        file_hash=digest,
        width_px=width,
        height_px=height,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        tags=None,
    )


def load_image(source: Any) -> Image.Image:
    """Return a :class:`PIL.Image.Image` from ``source`` recording metadata."""

    if isinstance(source, Image.Image):
        return source.copy()

    if isinstance(source, (str, Path)):
        path = Path(source)
        image = Image.open(path)
        _record_asset(image, name=path.name, path=path, data=None)
        return image

    if isinstance(source, (bytes, bytearray, memoryview)):
        payload = bytes(source)
        buffer = io.BytesIO(payload)
        image = Image.open(buffer)
        _record_asset(image, name=None, path=None, data=payload)
        return image

    if hasattr(source, "read"):
        stream: BinaryIO = source  # type: ignore[assignment]
        path = None
        stream_name = getattr(stream, "name", None)
        if isinstance(stream_name, str):
            try:
                candidate = Path(stream_name)
            except (TypeError, ValueError):
                candidate = None
            else:
                if candidate and candidate.exists():
                    path = candidate
        if path is not None:
            image = Image.open(path)
            _record_asset(image, name=path.name, path=path, data=None)
            return image
        try:
            position = stream.tell()
        except Exception:
            position = None
        payload = stream.read()
        if position is not None:
            try:
                stream.seek(position)
            except Exception:
                pass
        buffer = io.BytesIO(payload)
        image = Image.open(buffer)
        _record_asset(image, name=stream_name if isinstance(stream_name, str) else None, path=None, data=payload)
        return image

    raise TypeError(f"Unsupported image source: {type(source)!r}")
