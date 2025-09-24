"""ZPL backend implementation."""

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

    def render(self, context: Mapping[str, Any]) -> str:
        parts: list[str] = ["^XA"]
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
        if copies > 1:
            parts.append(f"^PQ{copies}")
        parts.append("^XZ")
        return "\n".join(parts) + "\n"

    # ------------------------------------------------------------------
    def _header(self) -> list[str]:
        width = self.mm_to_dots_x(float(self.template.get("width_mm", 0)))
        height = self.mm_to_dots_y(float(self.template.get("height_mm", 0)))
        header = []
        if width:
            header.append(f"^PW{width}")
        if height:
            header.append(f"^LL{height}")
        darkness = self.template.get("darkness")
        if darkness is not None:
            header.append(f"^MD{int(darkness)}")
        return header

    def _render_text(self, element: Mapping[str, Any], context: Mapping[str, Any]) -> str | None:
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
            return (
                f"^FO{x},{y}^A{font_name}{orientation},{height},{width}^FD{text}^FS"
            )

        bitmap = render_text_bitmap(text, font_spec)
        return self._graphic_field(element, bitmap)

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
        return (
            f"^FO{x},{y}^BC{orientation},{height},{human},N,N^FD{text}^FS"
        )

    def _render_qr(self, element: Mapping[str, Any], context: Mapping[str, Any]) -> str | None:
        value = self.resolve(element.get("value"), context)
        if value in (None, ""):
            return None
        text = self.sanitize(str(value))
        scale = self.dimension(element, "cell", axis="x", minimum=1)
        scale = max(1, min(10, scale))
        x = self.position(element, "x")
        y = self.position(element, "y")
        return f"^FO{x},{y}^BQN,2,{scale}^FDLA,{text}^FS"

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
        return self._graphic_field(element, image)

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
        return f"^FO{x},{y}^GB{width},{height},{thickness},{color},{rounding}^FS"

    # ------------------------------------------------------------------
    def _load_image(self, source: Any, element: Mapping[str, Any]) -> Image.Image:
        image = image_from_source(source)
        return self.fit_image(image, element)

    def _graphic_field(self, element: Mapping[str, Any], image: Image.Image) -> str:
        prepared = self.fit_image(image, element)
        hex_data, width_bytes, height = to_hex_bitmap(prepared)
        total_bytes = width_bytes * height
        x = self.position(element, "x")
        y = self.position(element, "y")
        return (
            f"^FO{x},{y}^GFA,{total_bytes},{total_bytes},{width_bytes},{hex_data}^FS"
        )


register_backend("zpl", ZPLBackend)
