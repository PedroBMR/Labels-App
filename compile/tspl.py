"""TSPL backend implementation."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from PIL import Image

from . import (
    Backend,
    Calibration,
    CompilationError,
    image_from_source,
    register_backend,
    render_text_bitmap,
    to_hex_bitmap,
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
    def render(self, context: Mapping[str, Any]) -> str:
        parts: list[str] = []
        parts.extend(self._header())
        for element in self.elements:
            handler = getattr(self, f"_render_{element.get('type')}", None)
            if handler is None:
                continue
            result = handler(element, context)
            if not result:
                continue
            if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
                parts.extend(str(item) for item in result)
            else:
                parts.append(str(result))
        copies = int(context.get("copies", self.template.get("print_copies", 1)) or 1)
        parts.append(f"PRINT {max(1, copies)}")
        return "\r\n".join(parts) + "\r\n"

    # ------------------------------------------------------------------
    def _header(self) -> list[str]:
        width = float(self.template.get("width_mm", 0))
        height = float(self.template.get("height_mm", 0))
        gap = float(self.template.get("gap_mm", 0))
        direction = int(self.template.get("direction", 1))

        header = [
            f"SIZE {width:g} mm,{height:g} mm",
            f"GAP {gap:g} mm,0",
        ]
        speed = self.template.get("speed")
        if speed is not None:
            header.append(f"SPEED {int(speed)}")
        density = self.template.get("density")
        if density is not None:
            header.append(f"DENSITY {int(density)}")
        header.append(f"DIRECTION {direction}")
        header.append("CLS")
        return header

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
            return (
                f'TEXT {x},{y},"{font_name}",{rotation},'
                f'{max(1, x_mul)},{max(1, y_mul)},"{text}"'
            )

        bitmap = render_text_bitmap(text, font_spec)
        return self._bitmap_command(element, bitmap)

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
        return (
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
        return f'QRCODE {x},{y},{error},{cell},{mode},{rotation},"{text}"'

    def _render_image(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        source = element.get("source")
        key = element.get("key")
        if key and key in context:
            source = context[key]
        if source in (None, ""):
            return None
        image = self._load_image(source, element)
        return self._bitmap_command(element, image)

    def _render_shape(
        self, element: Mapping[str, Any], context: Mapping[str, Any]
    ) -> str | None:
        kind = str(element.get("kind", "line")).lower()
        x = self.position(element, "x")
        y = self.position(element, "y")
        if kind in {"line", "bar"}:
            width = self.dimension(element, "width", axis="x", minimum=1)
            height = self.dimension(element, "height", axis="y", minimum=1)
            return f"BAR {x},{y},{width},{height}"
        if kind in {"rect", "rectangle", "box"}:
            width = self.dimension(element, "width", axis="x", minimum=1)
            height = self.dimension(element, "height", axis="y", minimum=1)
            thickness = self.dimension(element, "thickness", axis="x", minimum=1)
            x2 = x + width
            y2 = y + height
            return f"BOX {x},{y},{x2},{y2},{thickness}"
        raise CompilationError(f"Unsupported TSPL shape '{kind}'")

    # ------------------------------------------------------------------
    def _load_image(self, source: Any, element: Mapping[str, Any]) -> Image.Image:
        image = image_from_source(source)
        return self.fit_image(image, element)

    def _bitmap_command(self, element: Mapping[str, Any], image: Image.Image) -> str:
        prepared = self.fit_image(image, element)
        hex_data, width_bytes, height = to_hex_bitmap(prepared)
        x = self.position(element, "x")
        y = self.position(element, "y")
        mode = int(element.get("mode", 0))
        return f"BITMAP {x},{y},{width_bytes},{height},{mode},{hex_data}"


register_backend("tspl", TSPLBackend)
