from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

try:
    Image.new("1", (1, 1))
except Exception:
    pytest.skip("Pillow não está disponível", allow_module_level=True)

from compile import Calibration
from compile.tspl import TSPLBackend
from compile.zpl import ZPLBackend
from imaging.raster import prepare_bitmap_for_tspl, tspl_bitmap_command


def _sample_image() -> Image.Image:
    img = Image.new("1", (8, 8), color=1)
    for i in range(8):
        img.putpixel((i, i), 0)
        img.putpixel((7 - i, i), 0)
    return img


def test_tspl_backend_snapshot():
    image = _sample_image()
    template = {
        "backend": "tspl",
        "width_mm": 50,
        "height_mm": 40,
        "gap_mm": 2,
        "direction": 1,
        "elements": [
            {
                "type": "text",
                "x_mm": 5,
                "y_mm": 5,
                "font": {"name": "3", "x": 1, "y": 1},
                "content": "Hello {name}",
            },
            {
                "type": "barcode",
                "x_mm": 5,
                "y_mm": 15,
                "height_mm": 10,
                "module_mm": 0.5,
                "value": "{code}",
            },
            {
                "type": "qr",
                "x_mm": 5,
                "y_mm": 28,
                "cell_mm": 2,
                "value": "{qr}",
            },
            {
                "type": "shape",
                "kind": "rect",
                "x_mm": 5,
                "y_mm": 35,
                "width_mm": 30,
                "height_mm": 4,
                "thickness_mm": 0.5,
            },
            {
                "type": "image",
                "x_mm": 35,
                "y_mm": 5,
                "source": image,
                "max_width_mm": 8,
                "max_height_mm": 8,
            },
        ],
    }

    backend = TSPLBackend(template, calibration=Calibration())
    result = backend.compile({"name": "World", "code": "123456", "qr": "HELLO"})

    assert result.startswith(b"SIZE 50 mm,40 mm\r\n")
    assert b"DIRECTION 1\r\n" in result
    assert b"REFERENCE 0,0\r\n" in result
    assert b"GAP 2,0\r\n" in result
    assert b"CLS\r\n" in result
    assert b"HOME\r\n" in result
    assert b'TEXT 40,40,"3",0,1,1,"Hello World"\r\n' in result
    assert b'BARCODE 40,120,"128",80,1,0,4,2,"123456"\r\n' in result
    assert b'QRCODE 40,224,M,16,A,0,"HELLO"\r\n' in result
    assert b"BOX 40,280,280,312,4\r\n" in result

    dpi = backend.dots_per_mm * 25.4
    width_bytes, height, mode, data = prepare_bitmap_for_tspl(
        image,
        dpi_x=dpi,
        dpi_y=dpi,
        width_mm=8,
        height_mm=8,
    )
    expected_bitmap = tspl_bitmap_command(280, 40, width_bytes, height, mode, data)
    assert expected_bitmap in result
    assert b"PRINT 1\r\n" in result
    assert result.endswith(b"FORMFEED\r\n")


def test_zpl_backend_snapshot():
    image = _sample_image()
    template = {
        "backend": "zpl",
        "width_mm": 50,
        "height_mm": 40,
        "gap_mm": 2,
        "elements": [
            {
                "type": "text",
                "x_mm": 5,
                "y_mm": 5,
                "font": {"name": "0"},
                "height_mm": 6,
                "width_mm": 4,
                "content": "Hello {name}",
            },
            {
                "type": "barcode",
                "x_mm": 5,
                "y_mm": 12,
                "height_mm": 10,
                "value": "{code}",
            },
            {
                "type": "qr",
                "x_mm": 5,
                "y_mm": 25,
                "cell_mm": 2,
                "value": "{qr}",
            },
            {
                "type": "shape",
                "kind": "line",
                "x_mm": 5,
                "y_mm": 30,
                "width_mm": 30,
                "height_mm": 1,
                "thickness_mm": 0.5,
            },
            {
                "type": "image",
                "x_mm": 30,
                "y_mm": 5,
                "source": image,
                "max_width_mm": 8,
                "max_height_mm": 8,
            },
        ],
    }

    backend = ZPLBackend(template, calibration=Calibration())
    result = backend.compile({"name": "World", "code": "123456", "qr": "HELLO"})

    assert result.startswith(b"^XA\n")
    assert b"^PW400\n" in result
    assert b"^LL320\n" in result
    assert b"^MMT\n" in result
    assert b"^FO40,40^A0N,48,32^FDHello World^FS\n" in result
    assert b"^FO40,96^BCN,80,Y,N,N^FD123456^FS\n" in result
    assert b"^FO40,200^BQN,2,10^FDLA,HELLO^FS\n" in result
    assert b"^FO40,240^GB240,4,4,B,0^FS\n" in result

    dpi = backend.dots_per_mm * 25.4
    width_bytes, height, _, data = prepare_bitmap_for_tspl(
        image,
        dpi_x=dpi,
        dpi_y=dpi,
        width_mm=8,
        height_mm=8,
    )
    total_bytes = width_bytes * height
    hex_data = data.hex().upper().encode("ascii")
    expected = (
        b"^FO240,40^GFA," +
        str(total_bytes).encode("ascii") +
        b"," + str(total_bytes).encode("ascii") +
        b"," + str(width_bytes).encode("ascii") +
        b"," + hex_data + b"^FS\n"
    )
    assert expected in result
    assert b"^PQ1\n" in result
    assert result.endswith(b"^XZ\n")


def test_tspl_text_bitmap_fallback():
    template = {
        "backend": "tspl",
        "width_mm": 30,
        "height_mm": 20,
        "gap_mm": 2,
        "elements": [
            {
                "type": "text",
                "x_mm": 2,
                "y_mm": 3,
                "font": {"name": "Custom", "size": 18},
                "content": "{greeting}",
            }
        ],
    }
    backend = TSPLBackend(template)
    output = backend.compile({"greeting": "Olá"})
    assert b"BITMAP" in output
    assert b"TEXT" not in output


def test_zpl_text_bitmap_fallback():
    template = {
        "backend": "zpl",
        "width_mm": 30,
        "height_mm": 20,
        "elements": [
            {
                "type": "text",
                "x_mm": 2,
                "y_mm": 3,
                "font": {"name": "Custom", "size": 18},
                "content": "{greeting}",
            }
        ],
    }
    backend = ZPLBackend(template)
    output = backend.compile({"greeting": "Olá"})
    assert b"^GFA" in output
    assert b"^A" not in output


def test_tspl_media_black_mark_and_calibration():
    template = {
        "backend": "tspl",
        "width_mm": 40,
        "height_mm": 30,
        "speed": 4,
        "density": 10,
        "direction": 0,
        "reference_x": 2,
        "reference_y": 1,
        "media_type": "black_mark",
        "mark_mm": 5,
        "mark_offset_mm": 0.7,
        "fine_offset_mm": 0.3,
        "calibrate_next_print": True,
        "elements": [],
    }

    backend = TSPLBackend(template)
    result = backend.compile({"copies": 3})

    header = result.decode("latin-1").split("\r\n")
    assert "SPEED 4" in header
    assert "DENSITY 10" in header
    assert "DIRECTION 0" in header
    assert "REFERENCE 2,1" in header
    assert "BLINE 5,0.7" in header
    assert "OFFSET 0.3" in header
    assert "BLINEDETECT" in header
    assert "PRINT 3" in header
    assert result.endswith(b"FORMFEED\r\n")


def test_zpl_media_black_mark_and_calibration():
    template = {
        "backend": "zpl",
        "width_mm": 40,
        "height_mm": 30,
        "darkness": 12,
        "print_rate": "B,2,2",
        "media_type": "black_mark",
        "calibrate_next_print": True,
        "elements": [],
    }

    backend = ZPLBackend(template)
    result = backend.compile({"copies": 2})

    assert result.startswith(b"^XA\n")
    assert b"^PW320\n" in result
    assert b"^LL240\n" in result
    assert b"^MMC\n" in result
    assert b"^MD12\n" in result
    assert b"^PRB,2,2\n" in result
    assert b"~JC\n" in result
    assert b"^PQ2\n" in result
