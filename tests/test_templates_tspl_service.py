"""Testes adicionais para templates, montagem de TSPL e PrinterService.

Responsabilidade:
    Verificar seleção e ajustes de templates, montagem de comandos TSPL
    e comportamento do PrinterService em cenários de sucesso e falha.

Dependências:
    - printing

Exemplo:
    $ pytest tests/test_templates_tspl_service.py
"""

import os
import sys
from copy import deepcopy

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from tests._fake_win32 import FakeWin32, fake_win32

sys.modules["win32print"] = fake_win32  # type: ignore[assignment]


def test_template_selection_and_adjustment():
    import printing

    tpl_alias = printing.aplicar_template("Padrão")
    tpl_direct = printing.aplicar_template("100x30")
    assert tpl_alias.largura_mm == tpl_direct.largura_mm
    assert tpl_alias.layout == tpl_direct.layout

    layout = deepcopy(tpl_direct.layout)
    small_tpl = printing.Template(
        largura_mm=30,
        altura_mm=10,
        gap_mm=2,
        direction=1,
        layout=layout,
    )
    printing._ajustar_altura_layout(small_tpl.layout, small_tpl.altura_mm)
    printing._ajustar_largura_layout(small_tpl.layout, small_tpl.largura_mm)

    max_x = small_tpl.largura_mm * printing.DOTS_MM
    max_y = small_tpl.altura_mm * printing.DOTS_MM
    for spec in small_tpl.layout.values():
        if isinstance(spec, dict):
            assert 0 <= spec["x"] <= max_x
            assert 0 <= spec["y"] <= max_y


def test_montar_tspl_expected_string(fake_logo_recurso):
    import printing

    tpl = printing.aplicar_template("100x30")

    dados = {
        "saida": "S1",
        "categoria": "C1",
        "emissor": "E1",
        "municipio": "M1",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }

    tspl = printing.montar_tspl(tpl, dados)

    layout = tpl.layout
    x_logo = printing._calc_logo_x(
        layout, tpl.largura_mm * printing.DOTS_MM, 1
    )
    expected = "\r\n".join(
        [
            f"SIZE {tpl.largura_mm} mm,{tpl.altura_mm} mm",
            f"GAP {tpl.gap_mm} mm,0",
            "DENSITY 8",
            "SPEED 4",
            f"DIRECTION {tpl.direction}",
            "CLS",
            (
                f'TEXT {layout["titulo"]["x"]},{layout["titulo"]["y"]},'
                f'"{layout["titulo"]["font"]}",0,'
                f'{layout["titulo"]["xm"]},{layout["titulo"]["ym"]},'
                '"CONIMS"'
            ),
            (
                f'TEXT {layout["saida"]["x"]},{layout["saida"]["y"]},'
                f'"{layout["saida"]["font"]}",0,'
                f'{layout["saida"]["xm"]},{layout["saida"]["ym"]},'
                '"Saida: S1"'
            ),
            (
                f'TEXT {layout["categoria"]["x"]},{layout["categoria"]["y"]},'
                f'"{layout["categoria"]["font"]}",0,'
                f'{layout["categoria"]["xm"]},{layout["categoria"]["ym"]},'
                '"Categoria: C1"'
            ),
            (
                f'TEXT {layout["emissor"]["x"]},{layout["emissor"]["y"]},'
                f'"{layout["emissor"]["font"]}",0,'
                f'{layout["emissor"]["xm"]},{layout["emissor"]["ym"]},'
                '"Emissor: E1"'
            ),
            (
                f'TEXT {layout["municipio"]["x"]},'
                f'{layout["municipio"]["y"]},'
                f'"{layout["municipio"]["font"]}",0,'
                f'{layout["municipio"]["xm"]},{layout["municipio"]["ym"]},'
                '"Municipio: M1"'
            ),
            (
                f'TEXT {layout["data"]["x"]},{layout["data"]["y"]},'
                f'"{layout["data"]["font"]}",0,'
                f'{layout["data"]["xm"]},{layout["data"]["ym"]},'
                '"Impresso em: 2024-01-01"'
            ),
            (
                f'TEXT {layout["fracao"]["x"]},{layout["fracao"]["y"]},'
                f'"{layout["fracao"]["font"]}",0,'
                f'{layout["fracao"]["xm"]},{layout["fracao"]["ym"]},'
                '"[ ] Fracao"'
            ),
            (
                f'TEXT {layout["fragil"]["x"]},{layout["fragil"]["y"]},'
                f'"{layout["fragil"]["font"]}",0,'
                f'{layout["fragil"]["xm"]},{layout["fragil"]["ym"]},'
                '"[ ] Fragil"'
            ),
            (
                f'TEXT {layout["numeracao"]["x"]},'
                f'{layout["numeracao"]["y"]},'
                f'"{layout["numeracao"]["font"]}",0,'
                f'{layout["numeracao"]["xm"]},{layout["numeracao"]["ym"]},'
                '"1 DE 1"'
            ),
            f"BITMAP {x_logo},{layout['logo_y']},1,1,0,A",
            "PRINT 1",
        ]
    ) + "\r\n"

    assert tspl == expected


def test_tspl_60x80_contains_text_and_logo():
    import printing

    tpl = printing.aplicar_template("60x80")
    dados = {
        "saida": "S1",
        "categoria": "C1",
        "emissor": "E1",
        "municipio": "M1",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }

    tspl = printing.montar_tspl(tpl, dados)

    assert "TEXT" in tspl
    assert "BITMAP" in tspl

    dots_y = tpl.altura_mm * printing.DOTS_MM
    for line in tspl.splitlines():
        if line.startswith("BITMAP "):
            parts = line.split(",")
            y = int(parts[1])
            h = int(parts[3])
            assert y + h <= dots_y
            break
    else:
        assert False, "BITMAP line not found"


def test_default_label_texts_flow_through_builds(monkeypatch, fake_logo_recurso):
    import printing

    template = printing.aplicar_template("100x30")

    monkeypatch.setitem(printing.DEFAULT_LABEL_TEXTS, "titulo", "NOVO TITULO")
    monkeypatch.setitem(printing.DEFAULT_LABEL_TEXTS, "fragil", "[X] FRAGIL")
    monkeypatch.setitem(printing.DEFAULT_LABEL_TEXTS, "saida", "Saida -> {saida}")

    builder = printing.TsplBuilder(template)
    dados = {
        "saida": "S1",
        "categoria": "C1",
        "emissor": "E1",
        "municipio": "M1",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }

    tspl = builder.build(dados)
    assert "NOVO TITULO" in tspl
    assert "[X] FRAGIL" in tspl
    assert "Saida -> S1" in tspl

    pagina_teste = builder.build_pagina_teste()
    assert "NOVO TITULO" in pagina_teste
    assert "[X] FRAGIL" in pagina_teste
    assert "Saida -> 000" in pagina_teste


def test_printer_service_success(monkeypatch):
    import printing

    class SuccessWin32(FakeWin32):
        pass

    fake = SuccessWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    service = printing.PrinterService(printer_name="dummy")
    ok, erro = service.send("ABC")
    assert ok and erro is None
    assert fake.written == [b"ABC"]


def test_printer_service_failure(monkeypatch):
    import printing

    class FailingWin32(FakeWin32):
        def StartDocPrinter(self, h, level, info):
            raise Exception("boom")

    fake = FailingWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    service = printing.PrinterService(printer_name="dummy")
    ok, erro = service.send("XYZ")
    assert not ok
    assert erro == {"code": -1, "message": "boom"}
