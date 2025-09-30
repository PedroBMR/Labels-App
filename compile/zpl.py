"""ZPL backend implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Mapping

try:  # pragma: no cover - optional dependency guard
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - Pillow missing at runtime
    Image = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL import Image as PILImage


def _require_pillow() -> None:
    if Image is None:
        raise RuntimeError(
            "Pillow must be installed to render ZPL bitmaps. "
            "Install the 'Pillow' package to enable this feature."
        )

from imaging.raster import fingerprint_image, prepare_bitmap_for_tspl
from printing_utils import ZPLMediaParams, emit_zpl_footer, emit_zpl_media_setup

from . import (
    Backend,
    Calibration,
    CompilationError,
    image_from_source,
    register_backend,
    render_text_bitmap,
)

__all__ = ["ZPLBackend"]


class ZPLBackend(Backend):
    """Render templates into ZPL-II command strings."""

    builtin_fonts = tuple("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def __init__(
        self,
        template: Mapping[str, Any],
        *,
        calibration: Calibration | None = None,
    ) -> None:
        super().__init__(template, calibration=calibration)

    def render(self, context: Mapping[str, Any]) -> bytes:
        parts: list[bytes] = []
        parts.extend(self._encode_lines(self._header()))
        for element in self.elements:
            handler = getattr(self, f"_render_{element.get('type')}", None)
            if handler is None:
                continue
            result = handler(element, context)
            if not result:
                continue
            if isinstance(result, Iterable) and not isinstance(
                result, (bytes, bytearray)
            ):
                parts.extend(self._ensure_bytes(item) for item in result)
            else:
                parts.append(self._ensure_bytes(result))
        copies = int(context.get("copies", self.template.get("print_copies", 1)) or 1)
        parts.extend(self._encode_lines(emit_zpl_footer(max(1, copies))))
        return b"".join(parts)

    # ------------------------------------------------------------------
    def _encode_lines(self, lines: Iterable[str]) -> list[bytes]:
        return [self._line(line) for line in lines]

    def _line(self, text: str) -> bytes:
        return text.encode("cp1252", errors="replace") + b"\n"

    def _ensure_bytes(self, value: Any) -> bytes:
        if isinstance(value, (bytes, bytearray)):
            data = bytes(value)
            if data.endswith((b"\r", b"\n")):
                return data
            return data + b"\n"
        return self._line(str(value))

    # ------------------------------------------------------------------
    def _header(self) -> list[str]:
        width = self.mm_to_dots_x(float(self.template.get("width_mm", 0)))
        height = self.mm_to_dots_y(float(self.template.get("height_mm", 0)))
        darkness = self.template.get("darkness")
        if darkness is None:
            darkness = self.template.get("density")
        print_rate = self.template.get("print_rate", self.template.get("print_speed"))
        media_type = str(self.template.get("media_type", "gap")).lower()
        calibrate = bool(self.template.get("calibrate_next_print"))

        params = ZPLMediaParams(
            width_dots=width or None,
            height_dots=height or None,
            darkness=int(darkness) if darkness is not None else None,
            print_rate=str(print_rate) if print_rate not in (None, "") else None,
            media_type=media_type,
            calibrate=calibrate,
        )
        return emit_zpl_media_setup(params)

    def _render_text(
        self,
        element: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str | None:
        value = self.resolve(element.get("content"), context)
        if value is None:
            return None
        text = self.sanitize(str(value))
        if not text and not element.get("allow_empty", False):
            return None

        font_spec = element.get("font", {})
        font_name = str(font_spec.get("name", "0")).upper()
        orientation = str(
            element.get("orientation", font_spec.get("orientation", "N"))
        ).upper() or "N"
        x = self.position(element, "x")
        y = self.position(element, "y")

        if font_name in self.builtin_fonts:
            height = self.dimension(element, "height", axis="y", minimum=0)
            if not height:
                height = int(font_spec.get("height", 0))
            width = self.dimension(element, "width", axis="x", minimum=0)
            if not width:
                width = int(font_spec.get("width", 0))
            return self._line(
                f"^FO{x},{y}^A{font_name}{orientation},{height},{width}^FD{text}^FS"
            )

        bitmap = render_text_bitmap(text, font_spec)
        return self._graphic_field(
            element, bitmap, digest=fingerprint_image(bitmap)
        )

    def _render_barcode(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        value = self.resolve(element.get("value"), context)
        if value in (None, ""):
            return None
        text = self.sanitize(str(value))
        orientation = str(element.get("orientation", "N")).upper() or "N"
        height = self.dimension(element, "height", axis="y", minimum=1)
        human = "Y" if element.get("human", True) else "N"
        x = self.position(element, "x")
        y = self.position(element, "y")
        return self._line(
            f"^FO{x},{y}^BC{orientation},{height},{human},N,N^FD{text}^FS"
        )

    def _render_qr(
        self,
        element: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str | None:
        value = self.resolve(element.get("value"), context)
        if value in (None, ""):
            return None
        text = self.sanitize(str(value))
        scale = self.dimension(element, "cell", axis="x", minimum=1)
        scale = max(1, min(10, scale))
        x = self.position(element, "x")
        y = self.position(element, "y")
        return self._line(f"^FO{x},{y}^BQN,2,{scale}^FDLA,{text}^FS")

    def _render_image(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        source = element.get("source")
        key = element.get("key")
        if key and key in context:
            source = context[key]
        if source in (None, ""):
            return None
        image, digest = self._load_image(source, element)
        return self._graphic_field(element, image, digest=digest)

    def _render_shape(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        kind = str(element.get("kind", "line")).lower()
        x = self.position(element, "x")
        y = self.position(element, "y")
        width = self.dimension(element, "width", axis="x", minimum=1)
        height = self.dimension(element, "height", axis="y", minimum=1)
        thickness = self.dimension(element, "thickness", axis="x", minimum=1)
        if kind == "line":
            if width >= height:
                height = thickness
            else:
                width = thickness
        elif kind in {"rect", "rectangle", "box"}:
            pass
        else:
            raise CompilationError(f"Unsupported ZPL shape '{kind}'")
        color = str(element.get("color", "B"))[:1].upper() or "B"
        rounding = int(element.get("rounding", 0))
        return self._line(
            f"^FO{x},{y}^GB{width},{height},{thickness},{color},{rounding}^FS"
        )

    # ------------------------------------------------------------------
    def _load_image(
        self, source: Any, element: Mapping[str, Any]
    ) -> tuple[Image.Image, str]:
        _require_pillow()
        image = image_from_source(source)
        image.load()
        return image, fingerprint_image(image)

    def _resolve_raster_settings(self, element: Mapping[str, Any]) -> dict[str, Any]:
        template_settings = {}
        page_settings = self.template.get("raster")
        if isinstance(page_settings, Mapping):
            template_settings.update(page_settings)
        for key in ("dither", "gamma", "sharpen", "fit", "invert", "threshold"):
            value = self.template.get(key)
            if value is not None and key not in template_settings:
                template_settings[key] = value
        settings = {**template_settings}
        for key in ("dither", "gamma", "sharpen", "fit", "invert", "threshold"):
            if key in element:
                settings[key] = element[key]
        return settings

    def _graphic_field(
        self,
        element: Mapping[str, Any],
        image: Image.Image,
        *,
        digest: str | None = None,
    ) -> bytes:
        _require_pillow()
        settings = self._resolve_raster_settings(element)
        width = self.optional_dimension(element, "width", axis="x")
        height = self.optional_dimension(element, "height", axis="y")
        max_width = self.optional_dimension(element, "max_width", axis="x")
        max_height = self.optional_dimension(element, "max_height", axis="y")
        width_dots = width or max_width
        height_dots = height or max_height

        dpi_x = self.dots_per_mm * 25.4 * self.calibration.scale_x
        dpi_y = self.dots_per_mm * 25.4 * self.calibration.scale_y

        dither = str(settings.get("dither", "floyd")).lower()
        gamma = settings.get("gamma")
        try:
            gamma_val = float(gamma) if gamma is not None else None
        except (TypeError, ValueError):
            gamma_val = None
        sharpen = bool(settings.get("sharpen", False))
        fit = str(settings.get("fit", "fit"))
        invert = bool(settings.get("invert", False))
        threshold = settings.get("threshold", 128)
        try:
            threshold_val = int(threshold)
        except (TypeError, ValueError):
            threshold_val = 128

        width_mm = element.get("width_mm") or element.get("max_width_mm")
        height_mm = element.get("height_mm") or element.get("max_height_mm")
        try:
            width_mm_val = float(width_mm) if width_mm is not None else None
        except (TypeError, ValueError):
            width_mm_val = None
        try:
            height_mm_val = float(height_mm) if height_mm is not None else None
        except (TypeError, ValueError):
            height_mm_val = None

        file_hash = settings.get("file_hash")
        if not isinstance(file_hash, str):
            file_hash = digest or fingerprint_image(image)

        width_bytes, height, _, data = prepare_bitmap_for_tspl(
            image,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            width_mm=width_mm_val,
            height_mm=height_mm_val,
            width_dots=width_dots,
            height_dots=height_dots,
            fit=fit,
            dither=dither,
            gamma=gamma_val,
            sharpen=sharpen,
            invert=invert,
            threshold=threshold_val,
            file_hash=file_hash,
        )
        total_bytes = width_bytes * height
        hex_data = data.hex().upper()
        x = self.position(element, "x")
        y = self.position(element, "y")
        return self._line(
            f"^FO{x},{y}^GFA,{total_bytes},{total_bytes},{width_bytes},{hex_data}^FS"
        )


register_backend("zpl", ZPLBackend)
