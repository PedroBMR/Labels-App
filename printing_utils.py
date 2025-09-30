"""Utility helpers shared across printing modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

# Approximate base width (in dots) for TSPL internal fonts
FONT_BASE_W: Mapping[str, int] = {
    "1": 8,
    "2": 12,
    "3": 16,
    "4": 24,
    "5": 32,
    "6": 40,
}


def text_width_dots(texto: str, font: str, xm: int) -> int:
    """Return the width of ``texto`` in dots for the given font and multiplier."""

    base = FONT_BASE_W.get(str(font), 12)
    xm = int(xm) if int(xm) > 0 else 1
    return len(str(texto)) * base * xm


def adjust_logo_position(
    layout: MutableMapping[str, object],
    largura_mm: int,
    dots_mm: int,
) -> None:
    """Adjust logo related fields in ``layout`` to fit within ``largura_mm``."""

    limite = largura_mm * dots_mm

    logo_largura = layout.get("logo_largura")
    if isinstance(logo_largura, int) and logo_largura > limite:
        layout["logo_largura"] = limite  # type: ignore[index]
        logo_largura = limite

    if "logo_x_mm" in layout:
        logo_x_mm = float(layout.get("logo_x_mm", 0))  # type: ignore[arg-type]
        largura_logo_mm = (logo_largura or 0) / dots_mm
        max_x_mm = max(0, largura_mm - largura_logo_mm)
        if logo_x_mm > max_x_mm:
            layout["logo_x_mm"] = max_x_mm  # type: ignore[index]
    elif "logo_x" in layout:
        logo_x = int(layout.get("logo_x", 0))  # type: ignore[arg-type]
        max_x = max(0, limite - int(logo_largura or 0))
        if logo_x > max_x:
            layout["logo_x"] = max_x  # type: ignore[index]


def sanitize_text(s: str | None) -> str:
    """Return ``s`` cleaned for TSPL commands."""

    if s is None:
        return ""
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace('"', "'")
    return s


# ---------------------------------------------------------------------------
# Media setup helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TSPLMediaParams:
    """Container describing the parameters needed for TSPL media setup."""

    width_mm: float
    height_mm: float
    speed: int | None = None
    density: int | None = None
    direction: int = 1
    reference_x: int = 0
    reference_y: int = 0
    media_type: str = "gap"
    gap_mm: float | None = None
    gap_offset_mm: float = 0.0
    mark_mm: float | None = None
    mark_offset_mm: float = 0.0
    fine_offset_mm: float = 0.0
    calibrate: bool = False


def emit_tspl_media_setup(params: TSPLMediaParams) -> list[str]:
    """Return the TSPL commands that configure the printer before a job."""

    media_type = (params.media_type or "gap").strip().lower()
    commands = [f"SIZE {max(params.width_mm, 0):g} mm,{max(params.height_mm, 0):g} mm"]

    if params.speed is not None:
        commands.append(f"SPEED {int(params.speed)}")
    if params.density is not None:
        commands.append(f"DENSITY {int(params.density)}")

    commands.append(f"DIRECTION {int(params.direction)}")
    reference = f"{max(params.reference_x, 0)},{max(params.reference_y, 0)}"
    commands.append(f"REFERENCE {reference}")

    if media_type == "black_mark":
        mark = params.mark_mm if params.mark_mm is not None else params.gap_mm or 0.0
        commands.append(f"BLINE {max(mark, 0):g},{params.mark_offset_mm:g}")
    else:
        gap = params.gap_mm if params.gap_mm is not None else 0.0
        commands.append(f"GAP {max(gap, 0):g},{params.gap_offset_mm:g}")

    if abs(params.fine_offset_mm) > 0.0001:
        commands.append(f"OFFSET {params.fine_offset_mm:g}")

    commands.append("CLS")
    commands.append("HOME")

    if params.calibrate:
        commands.append("BLINEDETECT" if media_type == "black_mark" else "GAPDETECT")

    return commands


def emit_tspl_print_footer(copies: int) -> list[str]:
    """Return the TSPL commands that finalise a print job."""

    qty = copies if copies > 0 else 1
    return [f"PRINT {qty}", "FORMFEED"]


@dataclass(slots=True)
class ZPLMediaParams:
    """Container describing the parameters needed for ZPL media setup."""

    width_dots: int | None = None
    height_dots: int | None = None
    darkness: int | None = None
    print_rate: str | None = None
    media_type: str = "gap"
    calibrate: bool = False


def emit_zpl_media_setup(params: ZPLMediaParams) -> list[str]:
    """Return the ZPL commands that configure the printer before a job."""

    commands = ["^XA"]
    if params.width_dots and params.width_dots > 0:
        commands.append(f"^PW{params.width_dots}")
    if params.height_dots and params.height_dots > 0:
        commands.append(f"^LL{params.height_dots}")
    if params.darkness is not None:
        commands.append(f"^MD{int(params.darkness)}")
    if params.print_rate:
        commands.append(f"^PR{params.print_rate}")

    media_type = (params.media_type or "gap").strip().lower()
    commands.append("^MMC" if media_type == "black_mark" else "^MMT")

    if params.calibrate:
        commands.append("~JC")

    return commands


def emit_zpl_footer(copies: int) -> list[str]:
    """Return the closing ZPL commands for a job."""

    qty = copies if copies > 0 else 1
    return [f"^PQ{qty}", "^XZ"]

