from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from imaging.raster import clear_raster_cache, prepare_bitmap_for_tspl


@pytest.fixture(autouse=True)
def reset_cache():
    clear_raster_cache()
    yield
    clear_raster_cache()


def test_prepare_bitmap_uses_disk_cache_hit(tmp_path, monkeypatch):
    image = Image.new("L", (16, 8), color=255)
    cache_path = tmp_path / "cached.bin"
    cache_payload = b"\xAA" * (2 * 8)
    cache_path.write_bytes(cache_payload)

    from db import store as db_store

    monkeypatch.setattr(db_store, "get_asset_id_by_hash", lambda *_args, **_kwargs: 42)

    def fake_find_raster_cache(*_args, **_kwargs):
        return cache_path

    monkeypatch.setattr(db_store, "find_raster_cache", fake_find_raster_cache)

    def fake_insert_raster_cache(**_kwargs):
        return cache_path

    monkeypatch.setattr(
        db_store,
        "insert_or_get_raster_cache",
        fake_insert_raster_cache,
    )

    def fail(*_args, **_kwargs):  # pragma: no cover - sanity guard
        raise AssertionError("Rasterisation should not occur on cache hit")

    monkeypatch.setattr("imaging.raster._dither_to_mono", fail)

    width_bytes, height, mode, data = prepare_bitmap_for_tspl(
        image,
        dpi_x=203,
        dpi_y=203,
        width_dots=image.width,
        height_dots=image.height,
        file_hash="hash",
    )

    assert width_bytes == 2
    assert height == 8
    assert mode == 0
    assert data == cache_payload

    from imaging.raster import _RASTER_CACHE

    cache_key = (
        "hash",
        image.width,
        image.height,
        (203, 203),
        "floyd",
        0.0,
        False,
        False,
        128,
    )
    assert _RASTER_CACHE[cache_key] == (width_bytes, height, mode, data)


def test_prepare_bitmap_disk_cache_miss(tmp_path, monkeypatch):
    image = Image.new("L", (16, 8), color=0)

    stored_calls: dict[str, object] = {}

    from db import store as db_store

    monkeypatch.setattr(db_store, "get_asset_id_by_hash", lambda *_args, **_kwargs: 7)

    def fake_find(*args, **kwargs):
        stored_calls["find"] = (args, kwargs)
        return None

    monkeypatch.setattr(db_store, "find_raster_cache", fake_find)

    def fake_insert(**kwargs):
        stored_calls["insert"] = kwargs
        return kwargs["cache_path"]

    monkeypatch.setattr(db_store, "insert_or_get_raster_cache", fake_insert)

    monkeypatch.setattr("imaging.raster.Path.home", lambda: Path(tmp_path))

    width_bytes, height, mode, data = prepare_bitmap_for_tspl(
        image,
        dpi_x=203,
        dpi_y=203,
        width_dots=image.width,
        height_dots=image.height,
        file_hash="hash",
    )

    assert width_bytes == 2
    assert height == 8
    assert mode == 0
    assert data

    cache_dir = Path(tmp_path) / ".labels-app" / "cache"
    cached_files = list(cache_dir.glob("*.bin"))
    assert len(cached_files) == 1
    cached_path = cached_files[0]
    assert cached_path.read_bytes() == data

    assert "find" in stored_calls
    find_args, _ = stored_calls["find"]
    assert find_args[0] == 7
    assert find_args[1] == 16
    assert find_args[2] == 8
    assert find_args[3] == (203, 203)
    assert find_args[4] == "floyd"
    assert find_args[5] == 0.0
    assert find_args[6] is False
    assert find_args[7] is False
    assert find_args[8] == 128

    assert "insert" in stored_calls
    insert_args = stored_calls["insert"]
    assert insert_args["asset_id"] == 7
    assert insert_args["width_dots"] == 16
    assert insert_args["height_dots"] == 8
    assert insert_args["dpi"] == (203, 203)
    assert insert_args["dither"] == "floyd"
    assert insert_args["gamma"] == 0.0
    assert insert_args["sharpen"] is False
    assert insert_args["invert"] is False
    assert insert_args["threshold"] == 128
    assert insert_args["cache_path"].resolve() == cached_path.resolve()

    from imaging.raster import _RASTER_CACHE

    cache_key = (
        "hash",
        image.width,
        image.height,
        (203, 203),
        "floyd",
        0.0,
        False,
        False,
        128,
    )
    assert _RASTER_CACHE[cache_key] == (width_bytes, height, mode, data)
