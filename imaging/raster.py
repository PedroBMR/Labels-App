"""High quality raster preparation helpers for thermal printers."""

from __future__ import annotations

import hashlib
import io
from typing import Iterable, Mapping, MutableMapping

from PIL import Image, ImageFilter, ImageOps

try:  # pragma: no cover - optional Pillow component
    from PIL import ImageCms  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    ImageCms = None  # type: ignore[assignment]

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
        return image.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)

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
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    if fit_mode == "fill" and width and height:
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        right = left + width
        bottom = top + height
        return resized.crop((left, top, right, bottom))

    return resized


def _dither_to_mono(image: Image.Image, *, method: str) -> Image.Image:
    if method == "threshold":
        table = [0] * 256
        for i in range(128, 256):
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
) -> tuple[int, int, int, bytes]:
    """Return TSPL compatible raster data for ``image``."""

    dots_x = width_dots or _mm_to_dots(width_mm, dpi_x)
    dots_y = height_dots or _mm_to_dots(height_mm, dpi_y)

    rounded_x = int(round(dpi_x))
    rounded_y = int(round(dpi_y))
    if rounded_x not in {203, 300} or rounded_y not in {203, 300}:
        raise ValueError("Thermal raster only supports 203 or 300 DPI")

    cache_key = None
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
        )
        if cache_key in _RASTER_CACHE:
            return _RASTER_CACHE[cache_key]

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

    mono = _dither_to_mono(resized, method=method)
    data = _pack_msb_first(mono, invert=invert)

    width_bytes = (mono.width + 7) // 8
    result = (width_bytes, mono.height, 0, data)
    if cache_key:
        _RASTER_CACHE[cache_key] = result
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

