from __future__ import annotations

from PIL import Image

from compile import Calibration, to_hex_bitmap
from compile.tspl import TSPLBackend
from compile.zpl import ZPLBackend


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

    hex_data, width_bytes, height = to_hex_bitmap(image)
    expected = (
        "SIZE 50 mm,40 mm\r\n"
        "GAP 2 mm,0\r\n"
        "DIRECTION 1\r\n"
        "CLS\r\n"
        'TEXT 40,40,"3",0,1,1,"Hello World"\r\n'
        'BARCODE 40,120,"128",80,1,0,4,2,"123456"\r\n'
        'QRCODE 40,224,M,16,A,0,"HELLO"\r\n'
        "BOX 40,280,280,312,4\r\n"
        f"BITMAP 280,40,{width_bytes},{height},0,{hex_data}\r\n"
        "PRINT 1\r\n"
    )
    assert result == expected


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

    hex_data, width_bytes, height = to_hex_bitmap(image)
    total_bytes = width_bytes * height
    expected = (
        "^XA\n"
        "^PW400\n"
        "^LL320\n"
        "^FO40,40^A0N,48,32^FDHello World^FS\n"
        "^FO40,96^BCN,80,Y,N,N^FD123456^FS\n"
        "^FO40,200^BQN,2,10^FDLA,HELLO^FS\n"
        "^FO40,240^GB240,4,4,B,0^FS\n"
        f"^FO240,40^GFA,{total_bytes},{total_bytes},{width_bytes},{hex_data}^FS\n"
        "^XZ\n"
    )
    assert result == expected


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
    assert "BITMAP" in output
    assert "TEXT" not in output


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
    assert "^GFA" in output
    assert "^A" not in output
