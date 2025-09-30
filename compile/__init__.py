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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

try:  # pragma: no cover - optional dependency guard
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
except ImportError:  # pragma: no cover - Pillow missing at runtime
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from PIL import Image as PILImage


def _require_pillow() -> None:
    if Image is None or ImageDraw is None or ImageFont is None:
        raise RuntimeError(
            "Pillow must be installed to render label graphics. "
            "Install the 'Pillow' package to enable this feature."
        )

from fonts import font_store
from imaging import load_image

__all__ = [
    "Backend",
    "Calibration",
    "CompilationError",
    "SafeDict",
    "get_backend",
    "image_from_source",
    "register_backend",
    "render_text_bitmap",
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

    try:
        return load_image(source)
    except TypeError as exc:
        raise CompilationError(
            f"Unsupported image source: {type(source)!r}"
        ) from exc
    except Exception as exc:  # pragma: no cover - passthrough for PIL errors
        raise CompilationError("Failed to load image") from exc


def render_text_bitmap(text: str, font_spec: Mapping[str, Any]) -> Image.Image:
    """Render ``text`` into a monochrome bitmap using Pillow."""

    _require_pillow()
    size = int(font_spec.get("size", 24))
    font_path = font_store.resolve_spec_path(font_spec.get("ttf"))
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

    def optional_dimension(
        self, element: Mapping[str, Any], name: str, *, axis: str
    ) -> int | None:
        key_dots = f"{name}_dots"
        if key_dots in element:
            return int(round(float(element[key_dots])))
        key_mm = f"{name}_mm"
        if key_mm in element:
            raw = float(element[key_mm])
            return (
                self.mm_to_dots_x(raw) if axis == "x" else self.mm_to_dots_y(raw)
            )
        return None

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

    def compile(self, variables: Mapping[str, Any]) -> bytes:
        data = dict(variables)
        items = data.pop("items", None)
        if items is None:
            contexts = [self.prepare_context(data)]
        else:
            contexts = [self.prepare_context({**data, **item}) for item in items]
        rendered = [self.render(ctx) for ctx in contexts]
        if rendered and isinstance(rendered[0], (bytes, bytearray)):
            return b"".join(bytes(part) for part in rendered)
        text = "".join(str(part) for part in rendered)
        return text.encode("ascii", errors="replace")

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
    def render(self, context: Mapping[str, Any]) -> bytes:
        """Render commands for a single label using ``context``."""


from . import tspl as _tspl  # noqa: E402,F401
from . import zpl as _zpl  # noqa: E402,F401
