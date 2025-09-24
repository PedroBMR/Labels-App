"""Pillow based preview rendering for label templates.

This module provides a small rendering pipeline that mirrors the
capabilities of the interactive editor.  Template definitions are
expressed in millimetres and follow the :class:`model.template.Template`
schema.  Each element is rasterised to a monochrome image using Pillow and
composited into a final preview that matches the printer resolution.

The renderer is intentionally liberal in what it accepts: both the new
editor specific attributes (font family, alignment, fit modes) and the
legacy printer centric keys (``x_mm``/``width_mm``) are supported.  The
output image is always greyscale (mode ``"L"``) so it can be embedded
directly into the preview widget or exported as a PNG for tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import qrcode
from PIL import Image, ImageDraw, ImageFont

try:  # pragma: no cover - optional dependency during runtime
    import barcode  # type: ignore
    from barcode.writer import ImageWriter  # type: ignore
except Exception:  # pragma: no cover - fallback when barcode is missing
    barcode = None
    ImageWriter = object  # type: ignore[assignment]

from compile import Calibration, SafeDict

__all__ = [
    "PreviewRenderer",
    "render_template",
    "render_element",
    "render_element_image",
]

_DEFAULT_DPI = 203
_MM_PER_INCH = 25.4


def _dots_per_mm(page: Mapping[str, Any]) -> float:
    dpi = page.get("dpi")
    if dpi:
        try:
            return float(dpi) / _MM_PER_INCH
        except (TypeError, ValueError):  # pragma: no cover - invalid data
            pass
    return float(page.get("dots_per_mm", _DEFAULT_DPI / _MM_PER_INCH))


def _value_from_element(
    element: Mapping[str, Any],
    name: str,
    *,
    axis: str,
    dots_per_mm: float,
    calibration: Calibration,
    default: float = 0.0,
) -> float:
    key_dots = f"{name}_dots"
    if key_dots in element:
        try:
            value = float(element[key_dots])
        except (TypeError, ValueError):  # pragma: no cover - invalid data
            value = default
        scale = calibration.scale_x if axis == "x" else calibration.scale_y
        return value * scale
    key_mm = f"{name}_mm"
    if key_mm in element:
        try:
            value = float(element[key_mm])
        except (TypeError, ValueError):  # pragma: no cover - invalid data
            value = default
        scale = calibration.scale_x if axis == "x" else calibration.scale_y
        return value * dots_per_mm * scale
    return default


def _ensure_size(value: float, minimum: int = 1) -> int:
    return max(minimum, int(round(value)))


def _resolve_font_path(font_spec: Mapping[str, Any]) -> str | None:
    ttf = font_spec.get("ttf")
    if isinstance(ttf, (str, Path)):
        return str(ttf)
    family = font_spec.get("family")
    if isinstance(family, str) and family.strip():
        # ``ImageFont`` cannot locate fonts by family name directly so we
        # look up common locations manually.  This intentionally checks a
        # handful of directories that exist on the supported platforms.
        candidates: list[Path] = []
        family_lower = family.lower().replace(" ", "")
        for directory in (
            Path.home() / ".fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path("C:/Windows/Fonts"),
        ):
            if not directory.exists():
                continue
            for path in directory.rglob("*.ttf"):
                stem = path.stem.lower().replace(" ", "")
                if stem == family_lower or stem.startswith(family_lower + "-"):
                    candidates.append(path)
        if candidates:
            return str(candidates[0])
    return None


def _load_font(font_spec: Mapping[str, Any], size: int) -> ImageFont.FreeTypeFont:
    size = max(6, int(size))
    path = _resolve_font_path(font_spec)
    try:
        if path:
            return ImageFont.truetype(path, size=size)
    except OSError:  # pragma: no cover - font lookup failure
        pass
    return ImageFont.load_default()


def _resolve_text(value: Any, context: Mapping[str, Any]) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value.format_map(context)
    return str(value)


def _text_alignment(element: Mapping[str, Any]) -> tuple[str, str]:
    align = str(element.get("align", "left")).lower()
    valign = str(element.get("valign", "top")).lower()
    if align not in {"left", "center", "right"}:
        align = "left"
    if valign not in {"top", "center", "bottom"}:
        valign = "top"
    return align, valign


def _simulate_bold(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str, font: ImageFont.ImageFont) -> None:
    x, y = position
    draw.text((x, y), text, font=font, fill=0)
    draw.text((x + 1, y), text, font=font, fill=0)


def _simulate_italic(mask: Image.Image, shear: float = 0.25) -> Image.Image:
    width, height = mask.size
    offset = int(round(height * shear))
    return mask.transform(
        (width + offset, height),
        Image.AFFINE,
        (1, shear, 0, 0, 1, 0),
        resample=Image.BICUBIC,
    )


def _render_text(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    width: int,
    height: int,
) -> Image.Image | None:
    text = _resolve_text(element.get("content"), context)
    if not text and not element.get("allow_empty", False):
        return None

    font_spec = element.get("font", {}) if isinstance(element.get("font"), Mapping) else {}
    point_size = int(font_spec.get("size", element.get("size", 20)))
    font = _load_font(font_spec, point_size)
    bold = bool(font_spec.get("bold"))
    italic = bool(font_spec.get("italic"))

    dummy = Image.new("L", (1, 1), color=255)
    dummy_draw = ImageDraw.Draw(dummy)
    bbox = dummy_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    if "width_mm" not in element and "width_dots" not in element:
        width = max(width, text_width + 8)
    if "height_mm" not in element and "height_dots" not in element:
        height = max(height, text_height + 4)

    canvas = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(canvas)
    align, valign = _text_alignment(element)

    if align == "center":
        x = (width - text_width) / 2 - bbox[0]
    elif align == "right":
        x = width - text_width - bbox[0]
    else:
        x = -bbox[0]
    if valign == "center":
        y = (height - text_height) / 2 - bbox[1]
    elif valign == "bottom":
        y = height - text_height - bbox[1]
    else:
        y = -bbox[1]

    if italic:
        mask = Image.new("L", (text_width, text_height), color=0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=255)
        mask = _simulate_italic(mask)
        mask_width, mask_height = mask.size
        if align == "center":
            x = (width - mask_width) / 2
        elif align == "right":
            x = width - mask_width
        else:
            x = 0
        if valign == "center":
            y = (height - mask_height) / 2
        elif valign == "bottom":
            y = height - mask_height
        else:
            y = 0
        canvas.paste(0, box=(int(x), int(y)), mask=mask)
    else:
        position = (x, y)
    if bold:
        _simulate_bold(draw, position, text, font)
    else:
        draw.text(position, text, font=font, fill=0)
    return canvas


def _render_barcode(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    width: int,
    height: int,
    *,
    dots_per_mm: float,
) -> Image.Image | None:
    if barcode is None:  # pragma: no cover - optional dependency missing
        return None
    value = _resolve_text(element.get("value"), context)
    if not value:
        return None
    sym = str(element.get("symbology", "code128"))
    if "module_mm" in element:
        module_mm = float(element.get("module_mm", 0.5))
    else:
        module = float(element.get("module", 1.0))
        module_mm = module / dots_per_mm
    module_width = max(module_mm, 0.1)
    writer = ImageWriter()
    options = {
        "module_width": module_width,
        "module_height": height,
        "quiet_zone": 1,
        "write_text": bool(element.get("human", True)),
        "text_distance": 1,
    }
    try:
        cls = barcode.get_barcode_class(sym)
    except Exception:  # pragma: no cover - invalid barcode type
        cls = barcode.get_barcode_class("code128")
    try:
        barcode_obj = cls(value, writer=writer)
        barcode_img = barcode_obj.render(options)
    except Exception:  # pragma: no cover - barcode rendering failure
        return None
    if barcode_img.mode != "L":
        barcode_img = barcode_img.convert("L")
    return barcode_img.resize((width, height), Image.Resampling.LANCZOS)


def _render_qrcode(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    width: int,
    height: int,
) -> Image.Image | None:
    value = _resolve_text(element.get("value"), context)
    if not value:
        return None
    error_map = {
        "l": qrcode.constants.ERROR_CORRECT_L,
        "m": qrcode.constants.ERROR_CORRECT_M,
        "q": qrcode.constants.ERROR_CORRECT_Q,
        "h": qrcode.constants.ERROR_CORRECT_H,
    }
    error = error_map.get(str(element.get("error", "m")).lower(), qrcode.constants.ERROR_CORRECT_M)
    qr = qrcode.QRCode(error_correction=error, box_size=1, border=0)
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image(fill_color=0, back_color=255).convert("L")
    return img.resize((width, height), Image.Resampling.NEAREST)


def _render_image(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    width: int,
    height: int,
) -> Image.Image | None:
    source = element.get("source")
    key = element.get("key")
    if key and key in context:
        source = context[key]
    if not source:
        return None
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        else:
            image = Image.open(source)
    except Exception:  # pragma: no cover - invalid image
        return None
    fit_mode = str(element.get("fit", element.get("mode", "contain"))).lower()
    if fit_mode == "cover":
        image = image.convert("L")
        ratio = max(width / image.width, height / image.height)
        new_size = (int(round(image.width * ratio)), int(round(image.height * ratio)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        left = (image.width - width) // 2
        top = (image.height - height) // 2
        return image.crop((left, top, left + width, top + height))
    image = image.convert("L")
    ratio = min(width / image.width, height / image.height)
    new_size = (int(round(image.width * ratio)), int(round(image.height * ratio)))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("L", (width, height), color=255)
    offset = ((width - resized.width) // 2, (height - resized.height) // 2)
    canvas.paste(resized, offset)
    return canvas


def _render_shape(
    element: Mapping[str, Any],
    width: int,
    height: int,
    *,
    dots_per_mm: float,
) -> Image.Image:
    canvas = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(canvas)
    kind = str(element.get("kind", "line")).lower()
    thickness = element.get("thickness_mm")
    if thickness is None:
        thickness = element.get("thickness_dots")
        if thickness is None:
            thickness = 0.25
    if isinstance(thickness, str):
        try:
            thickness = float(thickness)
        except ValueError:
            thickness = 0.25
    if thickness <= 0:
        thickness = 0.25
    if element.get("kind") == "line" or kind == "line":
        pen = max(1, int(round(thickness * dots_per_mm)))
        draw.rectangle((0, height // 2 - pen // 2, width, height // 2 + pen // 2), fill=0)
    else:
        pen = max(1, int(round(thickness * dots_per_mm)))
        draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=pen)
    return canvas


def render_element_image(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    page: Mapping[str, Any],
    *,
    calibration: Calibration | None = None,
) -> tuple[Image.Image, int, int] | None:
    """Render an element to an image without applying rotation."""

    calibration = calibration or Calibration()
    dots_per_mm = _dots_per_mm(page)
    width = _value_from_element(
        element,
        "width",
        axis="x",
        dots_per_mm=dots_per_mm,
        calibration=calibration,
        default=float(page.get("width_mm", 0)) * dots_per_mm,
    )
    height = _value_from_element(
        element,
        "height",
        axis="y",
        dots_per_mm=dots_per_mm,
        calibration=calibration,
        default=float(page.get("height_mm", 0)) * dots_per_mm,
    )
    width_px = _ensure_size(width)
    height_px = _ensure_size(height)

    element_type = str(element.get("type", "text")).lower()
    if element_type == "text":
        content = _render_text(element, context, width_px, height_px)
    elif element_type == "barcode":
        content = _render_barcode(
            element,
            context,
            width_px,
            height_px,
            dots_per_mm=dots_per_mm,
        )
    elif element_type in {"qr", "qrcode"}:
        content = _render_qrcode(element, context, width_px, height_px)
    elif element_type == "image":
        content = _render_image(element, context, width_px, height_px)
    elif element_type == "shape":
        content = _render_shape(element, width_px, height_px, dots_per_mm=dots_per_mm)
    else:  # pragma: no cover - unsupported element
        return None

    if content is None:
        return None

    rotation = float(element.get("rotation", 0))
    return content, width_px, height_px


def render_element(
    element: Mapping[str, Any],
    context: Mapping[str, Any],
    page: Mapping[str, Any],
    *,
    calibration: Calibration | None = None,
) -> tuple[Image.Image, tuple[int, int]] | None:
    """Render a single element and return the image plus placement."""

    calibration = calibration or Calibration()
    base = render_element_image(
        element,
        context,
        page,
        calibration=calibration,
    )
    if not base:
        return None
    content, width_px, height_px = base

    rotation = float(element.get("rotation", 0))
    if rotation:
        content = content.rotate(-rotation, expand=True, fillcolor=255)

    dots_per_mm = _dots_per_mm(page)
    x = _value_from_element(
        element,
        "x",
        axis="x",
        dots_per_mm=dots_per_mm,
        calibration=calibration,
        default=0.0,
    )
    y = _value_from_element(
        element,
        "y",
        axis="y",
        dots_per_mm=dots_per_mm,
        calibration=calibration,
        default=0.0,
    )

    if rotation:
        offset_x = int(round(x - (content.width - width_px) / 2))
        offset_y = int(round(y - (content.height - height_px) / 2))
    else:
        offset_x = int(round(x))
        offset_y = int(round(y))
    return content, (offset_x, offset_y)


@dataclass(slots=True)
class PreviewRenderer:
    """Rasterise templates into Pillow images."""

    page: Mapping[str, Any]
    calibration: Calibration = Calibration()
    dots_per_mm: float = field(init=False)
    width: int = field(init=False)
    height: int = field(init=False)

    def __post_init__(self) -> None:
        self.page = dict(self.page)
        self.dots_per_mm = _dots_per_mm(self.page)
        width_mm = float(self.page.get("width_mm", 0))
        height_mm = float(self.page.get("height_mm", 0))
        self.width = _ensure_size(
            width_mm * self.dots_per_mm * self.calibration.scale_x,
            minimum=1,
        )
        self.height = _ensure_size(
            height_mm * self.dots_per_mm * self.calibration.scale_y,
            minimum=1,
        )

    def render(
        self,
        elements: Iterable[Mapping[str, Any]],
        variables: Mapping[str, Any] | None = None,
    ) -> Image.Image:
        context = SafeDict(dict(variables or {}))
        image = Image.new("L", (self.width, self.height), color=255)
        for element in elements:
            result = render_element(
                element,
                context,
                self.page,
                calibration=self.calibration,
            )
            if not result:
                continue
            content, (x, y) = result
            mask = None
            if content.mode != "L":
                mask = content.convert("L")
            image.paste(content, (x, y), mask=mask)
        return image


def render_template(
    template: Mapping[str, Any],
    variables: Mapping[str, Any] | None = None,
    *,
    calibration: Calibration | None = None,
) -> Image.Image:
    """Render ``template`` into a Pillow image."""

    page = template.get("page", template)
    elements = template.get("elements", [])
    renderer = PreviewRenderer(page, calibration=calibration or Calibration())
    return renderer.render(elements, variables or {})
