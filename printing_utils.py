"""Utility helpers for printing-related routines.

This module centralizes small helpers shared across modules, such as
font size calculations, logo positioning adjustments and text
sanitization.
"""

from __future__ import annotations

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


def text_height_dots(font: str, ym: int) -> int:
    """Return the height of a font in dots considering ``ym`` multiplier."""
    base = FONT_BASE_W.get(str(font), 12)
    ym = int(ym) if int(ym) > 0 else 1
    return base * ym


def adjust_logo_position(
    layout: MutableMapping[str, object],
    largura_mm: int,
    dots_mm: int,
) -> None:
    """Adjust logo related fields in ``layout`` to fit within ``largura_mm``.

    ``layout`` is modified in-place when necessary.
    """
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
