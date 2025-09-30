"""High quality raster preparation helpers for thermal printers."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable, MutableMapping
from pathlib import Path

try:  # pragma: no cover - optional dependency guard
    from PIL import Image, ImageFilter, ImageOps  # type: ignore
except ImportError:  # pragma: no cover - Pillow missing at runtime
    Image = ImageFilter = ImageOps = None  # type: ignore[assignment]

try:  # pragma: no cover - optional Pillow component
    from PIL import ImageCms  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ImageCms = None  # type: ignore[assignment]


def _require_pillow() -> None:
    if Image is None or ImageFilter is None or ImageOps is None:
        raise RuntimeError(
            "Pillow must be installed to rasterise images. "
            "Install the 'Pillow' package to enable this feature."
        )

__all__ = [
    "clear_raster_cache",
    "prepare_bitmap_for_tspl",
    "tspl_bitmap_command",
    "fingerprint_image",
]

_MM_PER_INCH = 25.4


def _mm_to_dots(size_mm: float | None, dpi: float) -> int | None:
    if size_mm is None:
        return None
    rounded = int(round(dpi))
    if rounded not in {203, 300}:
        raise ValueError(f"Unsupported DPI {dpi!r}; expected 203 or 300")
    return max(1, int(round(size_mm * dpi / _MM_PER_INCH)))


class _Cache(MutableMapping[tuple, tuple[int, int, int, bytes]]):
    def __init__(self) -> None:
        self._data: dict[tuple, tuple[int, int, int, bytes]] = {}

    def __getitem__(self, key: tuple) -> tuple[int, int, int, bytes]:
        return self._data[key]

    def __setitem__(self, key: tuple, value: tuple[int, int, int, bytes]) -> None:
        self._data[key] = value

    def __delitem__(self, key: tuple) -> None:
        del self._data[key]

    def __iter__(self) -> Iterable[tuple]:  # pragma: no cover - trivial
        return iter(self._data)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._data)


_RASTER_CACHE: _Cache = _Cache()


def clear_raster_cache() -> None:
    """Remove all cached rasterised bitmaps."""

    _RASTER_CACHE.clear()


def _composite_alpha(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        alpha_image = image.convert("RGBA")
        background = Image.new("RGBA", alpha_image.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(background, alpha_image)
        return composited.convert("RGB")
    if image.mode == "P":
        return image.convert("RGB")
    if image.mode in {"CMYK", "YCbCr"}:
        return image.convert("RGB")
    return image.convert("RGB") if image.mode not in {"RGB", "L"} else image


def _ensure_srgb(image: Image.Image) -> Image.Image:
    if ImageCms is not None:
        try:
            profile = image.info.get("icc_profile")
            if profile:
                profile_io = io.BytesIO(profile)
                srgb_profile = ImageCms.createProfile("sRGB")
                src_profile = ImageCms.ImageCmsProfile(profile_io)
                return ImageCms.profileToProfile(
                    image, src_profile, srgb_profile
                ).convert("RGB")
        except Exception:  # pragma: no cover - depends on Pillow configuration
            pass
    if image.mode not in {"RGB", "L"}:
        return image.convert("RGB")
    return image


def _apply_gamma(image: Image.Image, gamma: float | None) -> Image.Image:
    if not gamma or gamma <= 0:
        return image
    inv_gamma = 1.0 / gamma
    lut = [int(round(pow(i / 255.0, inv_gamma) * 255)) for i in range(256)]
    bands = len(image.getbands())
    return image.point(lut * bands)


def _resize_image(
    image: Image.Image,
    target_width: int | None,
    target_height: int | None,
    *,
    fit: str,
) -> Image.Image:
    fit_mode = fit.lower()
    width = max(1, int(round(target_width))) if target_width else None
    height = max(1, int(round(target_height))) if target_height else None
    if width is None and height is None:
        return image

    src_w, src_h = image.size
    if fit_mode == "stretch":
        width = width or src_w
        height = height or src_h
        return image.resize(
            (max(1, width), max(1, height)),
            Image.Resampling.LANCZOS,
        )

    scale_x = width / src_w if width else None
    scale_y = height / src_h if height else None

    if fit_mode == "fill" and width and height:
        scale = max(scale_x or 0, scale_y or 0)
    else:
        candidates = [value for value in (scale_x, scale_y) if value and value > 0]
        if not candidates:
            scale = scale_x or scale_y or 1.0
        else:
            scale = min(candidates)

    new_width = max(1, int(round(src_w * scale)))
    new_height = max(1, int(round(src_h * scale)))
    resized = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    if fit_mode == "fill" and width and height:
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        right = left + width
        bottom = top + height
        return resized.crop((left, top, right, bottom))

    return resized


def _dither_to_mono(
    image: Image.Image,
    *,
    method: str,
    threshold: int = 128,
) -> Image.Image:
    if method == "threshold":
        cut = max(0, min(255, int(threshold)))
        table = [0] * 256
        for i in range(cut, 256):
            table[i] = 255
        return image.point(table, mode="1")
    if method == "bayer":
        return image.convert("1", dither=Image.Dither.ORDERED)
    return image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def _pack_msb_first(image: Image.Image, *, invert: bool) -> bytes:
    width_bytes = (image.width + 7) // 8
    padded_width = width_bytes * 8
    pixels = image.load()
    if pixels is None:  # pragma: no cover - Pillow internal failure
        raise RuntimeError("Image pixels could not be loaded")

    data = bytearray()
    for y in range(image.height):
        byte = 0
        bits = 0
        for x in range(padded_width):
            if x < image.width and pixels[x, y] == 0:
                bit = 1
            else:
                bit = 0
            if invert:
                bit ^= 1
            byte = (byte << 1) | bit
            bits += 1
            if bits == 8:
                data.append(byte)
                byte = 0
                bits = 0
        if bits:
            data.append(byte << (8 - bits))
    return bytes(data)


def _default_cache_dir() -> Path:
    return Path.home() / ".labels-app" / "cache"


def prepare_bitmap_for_tspl(
    image: Image.Image,
    *,
    dpi_x: float,
    dpi_y: float,
    width_mm: float | None = None,
    height_mm: float | None = None,
    width_dots: int | None = None,
    height_dots: int | None = None,
    fit: str = "fit",
    dither: str = "floyd",
    gamma: float | None = None,
    sharpen: bool = False,
    invert: bool = False,
    file_hash: str | None = None,
    threshold: int | None = None,
) -> tuple[int, int, int, bytes]:
    """Return TSPL compatible raster data for ``image``.

    The raster is cached in-memory and, when possible, on disk. The disk cache is
    optional and silently ignored when the cache directory cannot be created or
    accessed.
    """

    _require_pillow()
    dots_x = width_dots or _mm_to_dots(width_mm, dpi_x)
    dots_y = height_dots or _mm_to_dots(height_mm, dpi_y)

    rounded_x = int(round(dpi_x))
    rounded_y = int(round(dpi_y))
    if rounded_x not in {203, 300} or rounded_y not in {203, 300}:
        raise ValueError("Thermal raster only supports 203 or 300 DPI")

    cache_key = None
    asset_id: int | None = None
    if file_hash:
        cache_key = (
            file_hash,
            dots_x or image.width,
            dots_y or image.height,
            (rounded_x, rounded_y),
            dither.lower(),
            float(gamma or 0),
            bool(sharpen),
            bool(invert),
            int(threshold if threshold is not None else 128),
        )
        if cache_key in _RASTER_CACHE:
            return _RASTER_CACHE[cache_key]
        try:
            from db import store as db_store

            asset_id = db_store.get_asset_id_by_hash(file_hash)
        except Exception:
            asset_id = None

    fit_mode = fit.lower()
    if fit_mode not in {"fit", "fill", "stretch"}:
        raise ValueError(f"Unknown fit mode: {fit}")

    method = dither.lower()
    if method not in {"bayer", "floyd", "threshold"}:
        raise ValueError(f"Unsupported dither method: {dither}")

    working = _ensure_srgb(_composite_alpha(image))
    if working.mode != "L":
        working = ImageOps.grayscale(working)

    working = _apply_gamma(working, gamma)
    resized = _resize_image(working, dots_x, dots_y, fit=fit_mode)

    if sharpen:
        resized = resized.filter(ImageFilter.UnsharpMask())

    width_bytes = (resized.width + 7) // 8
    padded_width = width_bytes * 8
    height_px = resized.height
    gamma_value = float(gamma) if gamma and gamma > 0 else 0.0
    threshold_value = int(threshold if threshold is not None else 128)

    if asset_id is not None:
        try:
            from db import store as db_store

            cache_path = db_store.find_raster_cache(
                asset_id,
                padded_width,
                height_px,
                (rounded_x, rounded_y),
                method,
                gamma_value,
                sharpen,
                invert,
                threshold_value,
            )
        except Exception:
            cache_path = None
        if cache_path is not None:
            try:
                payload = cache_path.read_bytes()
            except OSError:
                payload = None
            else:
                result = (width_bytes, height_px, 0, payload)
                if cache_key:
                    _RASTER_CACHE[cache_key] = result
                return result

    mono = _dither_to_mono(
        resized,
        method=method,
        threshold=threshold_value,
    )
    data = _pack_msb_first(mono, invert=invert)

    final_width_bytes = (mono.width + 7) // 8
    padded_width = final_width_bytes * 8
    result = (final_width_bytes, mono.height, 0, data)

    if cache_key:
        _RASTER_CACHE[cache_key] = result

    if asset_id is not None:
        cache_dir = _default_cache_dir()
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            cache_dir = None

        if cache_dir is not None:
            descriptor = ":".join(
                [
                    str(file_hash or asset_id),
                    str(padded_width),
                    str(mono.height),
                    str(rounded_x),
                    str(rounded_y),
                    method,
                    str(gamma_value),
                    str(int(bool(sharpen))),
                    str(int(bool(invert))),
                    str(threshold_value),
                ]
            )
            digest = hashlib.sha1(descriptor.encode("utf-8")).hexdigest()
            prefix = file_hash or f"asset{asset_id}"
            filename = f"{prefix}_{digest}.bin"
            cache_path = cache_dir / filename
            try:
                cache_path.write_bytes(data)
            except OSError:
                pass
            else:
                try:
                    from db import store as db_store

                    # The raster cache is keyed by the rendering parameters to avoid
                    # recomputing identical bitmaps. ``db.store`` exposes helpers for
                    # inserting or querying cache entries and keeps the schema details
                    # (column names, uniqueness rules, etc.) in one place.
                    db_store.insert_or_get_raster_cache(
                        asset_id=asset_id,
                        width_dots=padded_width,
                        height_dots=mono.height,
                        dpi=(rounded_x, rounded_y),
                        dither=method,
                        gamma=gamma_value,
                        sharpen=sharpen,
                        invert=invert,
                        threshold=threshold_value,
                        cache_path=cache_path,
                    )
                except Exception:
                    pass

    return result


def tspl_bitmap_command(
    x: int,
    y: int,
    width_bytes: int,
    height_dots: int,
    mode: int,
    data: bytes,
) -> bytes:
    """Return a fully assembled ``BITMAP`` command for TSPL printers."""

    header = f"BITMAP {x},{y},{width_bytes},{height_dots},{mode},".encode("ascii")
    return header + data + b"\r\n"


def fingerprint_image(image: Image.Image) -> str:
    """Return a stable digest identifying ``image`` contents."""

    _require_pillow()
    try:
        image.load()
    except Exception:  # pragma: no cover - depends on Pillow backend
        pass
    with io.BytesIO() as buffer:
        base = image
        if image.mode not in {"RGB", "L"}:
            base = image.convert("RGB")
        base.save(buffer, format="PNG")
        payload = buffer.getvalue()
    return hashlib.sha1(payload).hexdigest()

