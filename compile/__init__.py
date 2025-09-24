"""Label compilation backends.

This package exposes a small plugin architecture used by the
:mod:`printing` module to transform high level template definitions into
printer command languages.  Each backend understands how to translate a
JSON template (positions expressed in millimetres) and a mapping of
resolved variables into commands for a specific printer firmware.

Two backends are bundled:

``tspl``
    Generates commands for printers that speak the TSPL/TSPL2 protocol
    (used by devices from TSC, Elgin and several OEM models).

``zpl``
    Generates ZPL-II commands for Zebra compatible printers.

Backends share a common :class:`Backend` base class that provides
convenience helpers such as millimetre to dot conversion,
context/placeholder resolution and bitmap generation via Pillow.  New
backends can be registered through :func:`register_backend`.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "Backend",
    "Calibration",
    "CompilationError",
    "SafeDict",
    "get_backend",
    "image_from_source",
    "register_backend",
    "render_text_bitmap",
    "to_hex_bitmap",
]


class CompilationError(RuntimeError):
    """Raised when a template cannot be rendered by the backend."""


class SafeDict(dict[str, Any]):
    """Mapping that never raises ``KeyError`` when formatting strings."""

    def __missing__(self, key: str) -> Any:  # pragma: no cover - defensive
        return ""


@dataclass(frozen=True)
class Calibration:
    """Container describing printer calibration ratios."""

    scale_x: float = 1.0
    scale_y: float = 1.0


def _dots_per_mm(template: Mapping[str, Any]) -> float:
    if "dots_per_mm" in template:
        value = float(template["dots_per_mm"])
        return value if value > 0 else 8.0
    dpi = template.get("dpi")
    if dpi:
        try:
            return float(dpi) / 25.4
        except (TypeError, ValueError):
            pass
    return 8.0


def image_from_source(source: Any) -> Image.Image:
    """Return a :class:`PIL.Image.Image` from ``source``."""

    if isinstance(source, Image.Image):
        return source.copy()
    if isinstance(source, (bytes, bytearray)):
        return Image.open(io.BytesIO(source))
    if isinstance(source, str):
        return Image.open(source)
    if hasattr(source, "read"):
        return Image.open(source)
    raise CompilationError(f"Unsupported image source: {type(source)!r}")


def render_text_bitmap(text: str, font_spec: Mapping[str, Any]) -> Image.Image:
    """Render ``text`` into a monochrome bitmap using Pillow."""

    size = int(font_spec.get("size", 24))
    font_path = font_spec.get("ttf")
    try:
        if font_path:
            font = ImageFont.truetype(str(font_path), size)
        else:
            font = ImageFont.load_default()
    except OSError:  # pragma: no cover - depends on font availability
        font = ImageFont.load_default()

    dummy = Image.new("L", (1, 1), color=255)
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])

    canvas = Image.new("1", (width, height), color=1)
    canvas_draw = ImageDraw.Draw(canvas)
    canvas_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=0)
    return canvas


def to_hex_bitmap(image: Image.Image) -> tuple[str, int, int]:
    """Convert ``image`` to TSPL/ZPL compatible hexadecimal data."""

    mono = image.convert("1")
    width_bytes = (mono.width + 7) // 8
    padded_width = width_bytes * 8

    pixels = mono.load()
    if pixels is None:  # pragma: no cover - pillow internal failure
        raise CompilationError("Image pixels could not be loaded")

    data = bytearray()
    for y in range(mono.height):
        byte = 0
        bits = 0
        for x in range(padded_width):
            if x < mono.width and pixels[x, y] == 0:
                bit = 1
            else:
                bit = 0
            byte = (byte << 1) | bit
            bits += 1
            if bits == 8:
                data.append(byte)
                byte = 0
                bits = 0
        if bits:
            data.append(byte << (8 - bits))
    return "".join(f"{b:02X}" for b in data), width_bytes, mono.height


_BACKENDS: dict[str, type["Backend"]] = {}


def register_backend(name: str, backend: type["Backend"]) -> None:
    """Register ``backend`` under ``name`` (case insensitive)."""

    _BACKENDS[name.lower()] = backend


def get_backend(
    name: str,
    template: Mapping[str, Any],
    *,
    calibration: Calibration | None = None,
    **kwargs: Any,
) -> "Backend":
    """Instantiate the backend ``name`` using ``template``."""

    try:
        backend_cls = _BACKENDS[name.lower()]
    except KeyError as exc:  # pragma: no cover - invalid usage
        raise CompilationError(f"Backend '{name}' is not registered") from exc
    return backend_cls(template, calibration=calibration, **kwargs)


class Backend(ABC):
    """Abstract base class for compilation backends."""

    builtin_fonts: tuple[str, ...] = ()

    def __init__(
        self,
        template: Mapping[str, Any],
        *,
        calibration: Calibration | None = None,
    ) -> None:
        self.template = template
        self.calibration = calibration or Calibration()
        self.dots_per_mm = _dots_per_mm(template)

    def _scale_x(self, value: float) -> float:
        return value * self.calibration.scale_x

    def _scale_y(self, value: float) -> float:
        return value * self.calibration.scale_y

    def mm_to_dots_x(self, value: float) -> int:
        return int(round(self._scale_x(value * self.dots_per_mm)))

    def mm_to_dots_y(self, value: float) -> int:
        return int(round(self._scale_y(value * self.dots_per_mm)))

    def position(self, element: Mapping[str, Any], axis: str) -> int:
        key_dots = f"{axis}_dots"
        if key_dots in element:
            value = float(element[key_dots])
            scale = (
                self.calibration.scale_x
                if axis == "x"
                else self.calibration.scale_y
            )
            return int(round(value * scale))
        key_mm = f"{axis}_mm"
        if key_mm in element:
            value = float(element[key_mm])
            return (
                self.mm_to_dots_x(value)
                if axis == "x"
                else self.mm_to_dots_y(value)
            )
        return 0

    def dimension(
        self,
        element: Mapping[str, Any],
        name: str,
        *,
        axis: str,
        minimum: int = 0,
    ) -> int:
        key_dots = f"{name}_dots"
        if key_dots in element:
            value = int(round(float(element[key_dots])))
        else:
            key_mm = f"{name}_mm"
            if key_mm in element:
                raw = float(element[key_mm])
                value = (
                    self.mm_to_dots_x(raw)
                    if axis == "x"
                    else self.mm_to_dots_y(raw)
                )
            else:
                value = 0
        return max(minimum, value)

    def prepare_context(self, variables: Mapping[str, Any]) -> SafeDict:
        return SafeDict(dict(variables))

    def resolve(self, value: Any, context: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            return value.format_map(context)
        return value

    def sanitize(self, text: str) -> str:
        return text.replace("\r", " ").replace("\n", " ").replace('"', "'")

    @property
    def elements(self) -> list[Mapping[str, Any]]:
        raw = self.template.get("elements", [])
        if isinstance(raw, (list, tuple)):
            return list(raw)
        return []

    def compile(self, variables: Mapping[str, Any]) -> str:
        data = dict(variables)
        items = data.pop("items", None)
        if items is None:
            contexts = [self.prepare_context(data)]
        else:
            contexts = [self.prepare_context({**data, **item}) for item in items]
        rendered = [self.render(ctx) for ctx in contexts]
        return "".join(rendered)

    def fit_image(self, image: Image.Image, element: Mapping[str, Any]) -> Image.Image:
        width_mm = element.get("max_width_mm")
        height_mm = element.get("max_height_mm")
        if width_mm is None and height_mm is None:
            return image

        width_limit = (
            self.mm_to_dots_x(float(width_mm)) if width_mm is not None else None
        )
        height_limit = (
            self.mm_to_dots_y(float(height_mm)) if height_mm is not None else None
        )

        orig_w, orig_h = image.size
        scale = 1.0
        if width_limit:
            scale = min(scale, width_limit / orig_w)
        if height_limit:
            scale = min(scale, height_limit / orig_h)
        if scale >= 1.0:
            return image

        new_size = (
            max(1, int(round(orig_w * scale))),
            max(1, int(round(orig_h * scale))),
        )
        return image.resize(new_size, Image.Resampling.LANCZOS)

    @abstractmethod
    def render(self, context: Mapping[str, Any]) -> str:
        """Render commands for a single label using ``context``."""


from . import tspl as _tspl  # noqa: E402,F401
from . import zpl as _zpl  # noqa: E402,F401
