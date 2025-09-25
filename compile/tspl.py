"""TSPL backend implementation."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from PIL import Image

from imaging.raster import (
    fingerprint_image,
    prepare_bitmap_for_tspl,
    tspl_bitmap_command,
)
from printing_utils import (
    TSPLMediaParams,
    emit_tspl_media_setup,
    emit_tspl_print_footer,
)

from . import (
    Backend,
    Calibration,
    CompilationError,
    image_from_source,
    register_backend,
    render_text_bitmap,
)

__all__ = ["TSPLBackend"]


class TSPLBackend(Backend):
    """Render templates into TSPL/TSPL2 command strings."""

    builtin_fonts = tuple(str(i) for i in range(9))

    def __init__(
        self,
        template: Mapping[str, Any],
        *,
        calibration: Calibration | None = None,
    ) -> None:
        super().__init__(template, calibration=calibration)

    # ------------------------------------------------------------------
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
            if isinstance(result, Iterable) and not isinstance(result, (bytes, bytearray)):
                parts.extend(self._ensure_bytes(item) for item in result)
            else:
                parts.append(self._ensure_bytes(result))
        copies = int(context.get("copies", self.template.get("print_copies", 1)) or 1)
        parts.extend(self._encode_lines(emit_tspl_print_footer(max(1, copies))))
        return b"".join(parts)

    # ------------------------------------------------------------------
    def _encode_lines(self, lines: Iterable[str]) -> list[bytes]:
        return [self._line(line) for line in lines]

    def _line(self, text: str) -> bytes:
        return text.encode("cp1252", errors="replace") + b"\r\n"

    def _ensure_bytes(self, value: Any) -> bytes:
        if isinstance(value, (bytes, bytearray)):
            data = bytes(value)
            if data.endswith(b"\n"):
                return data
            return data + b"\r\n"
        return self._line(str(value))

    # ------------------------------------------------------------------
    def _header(self) -> list[str]:
        width = float(self.template.get("width_mm", 0))
        height = float(self.template.get("height_mm", 0))
        def _int_setting(value: Any) -> int | None:
            try:
                if value in (None, ""):
                    return None
                number = int(float(value))
            except (TypeError, ValueError):
                return None
            return number

        speed = _int_setting(self.template.get("speed"))
        density = _int_setting(
            self.template.get("density", self.template.get("darkness"))
        )
        direction = int(self.template.get("direction", 1))
        reference_x = int(self.template.get("reference_x", 0))
        reference_y = int(self.template.get("reference_y", 0))

        media_type = str(self.template.get("media_type", "gap")).lower()
        gap_mm = self.template.get("gap_mm")
        gap_offset = float(self.template.get("gap_offset_mm", 0.0))
        mark_mm = self.template.get("mark_mm", self.template.get("black_mark_mm"))
        mark_offset = float(
            self.template.get("mark_offset_mm", self.template.get("black_mark_offset_mm", 0.0))
        )
        fine_offset = float(self.template.get("fine_offset_mm", 0.0))
        calibrate = bool(self.template.get("calibrate_next_print"))

        params = TSPLMediaParams(
            width_mm=width,
            height_mm=height,
            speed=speed,
            density=density,
            direction=direction,
            reference_x=reference_x,
            reference_y=reference_y,
            media_type=media_type,
            gap_mm=float(gap_mm) if gap_mm is not None else None,
            gap_offset_mm=gap_offset,
            mark_mm=float(mark_mm) if mark_mm is not None else None,
            mark_offset_mm=mark_offset,
            fine_offset_mm=fine_offset,
            calibrate=calibrate,
        )
        return emit_tspl_media_setup(params)

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
        font_name = str(font_spec.get("name", "0"))
        x = self.position(element, "x")
        y = self.position(element, "y")
        rotation = int(element.get("rotation", 0))
        x_mul = int(font_spec.get("x", font_spec.get("xm", 1)))
        y_mul = int(font_spec.get("y", font_spec.get("ym", 1)))

        if font_name in self.builtin_fonts:
            return self._line(
                f'TEXT {x},{y},"{font_name}",{rotation},'
                f'{max(1, x_mul)},{max(1, y_mul)},"{text}"'
            )

        bitmap = render_text_bitmap(text, font_spec)
        return self._bitmap_command(element, bitmap, digest=fingerprint_image(bitmap))

    def _render_barcode(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        value = self.resolve(element.get("value"), context)
        if value in (None, ""):
            return None
        text = self.sanitize(str(value))
        sym = str(element.get("symbology", "128"))
        height = self.dimension(element, "height", axis="y", minimum=1)
        module = self.dimension(element, "module", axis="x", minimum=1)
        ratio = int(element.get("ratio", 2))
        rotation = int(element.get("rotation", 0))
        human = int(bool(element.get("human", True)))
        x = self.position(element, "x")
        y = self.position(element, "y")
        return self._line(
            f'BARCODE {x},{y},"{sym}",{height},{human},{rotation},{module},'
            f'{max(1, ratio)},"{text}"'
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
        error = str(element.get("error", "M"))
        cell = self.dimension(element, "cell", axis="x", minimum=1)
        mode = str(element.get("mode", "A"))
        rotation = int(element.get("rotation", 0))
        x = self.position(element, "x")
        y = self.position(element, "y")
        return self._line(
            f'QRCODE {x},{y},{error},{cell},{mode},{rotation},"{text}"'
        )

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
        return self._bitmap_command(element, image, digest=digest)

    def _render_shape(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        kind = str(element.get("kind", "line")).lower()
        x = self.position(element, "x")
        y = self.position(element, "y")
        if kind in {"line", "bar"}:
            width = self.dimension(element, "width", axis="x", minimum=1)
            height = self.dimension(element, "height", axis="y", minimum=1)
            return self._line(f"BAR {x},{y},{width},{height}")
        if kind in {"rect", "rectangle", "box"}:
            width = self.dimension(element, "width", axis="x", minimum=1)
            height = self.dimension(element, "height", axis="y", minimum=1)
            thickness = self.dimension(element, "thickness", axis="x", minimum=1)
            x2 = x + width
            y2 = y + height
            return self._line(f"BOX {x},{y},{x2},{y2},{thickness}")
        raise CompilationError(f"Unsupported TSPL shape '{kind}'")

    # ------------------------------------------------------------------
    def _load_image(
        self, source: Any, element: Mapping[str, Any]
    ) -> tuple[Image.Image, str]:
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

    def _bitmap_command(
        self, element: Mapping[str, Any], image: Image.Image, *, digest: str | None = None
    ) -> bytes:
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

        width_bytes, height, mode, data = prepare_bitmap_for_tspl(
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

        x = self.position(element, "x")
        y = self.position(element, "y")
        element_mode = element.get("mode")
        if element_mode is not None:
            try:
                mode = int(element_mode)
            except (TypeError, ValueError):
                mode = 0
        command = tspl_bitmap_command(x, y, width_bytes, height, mode, data)
        return command


register_backend("tspl", TSPLBackend)
