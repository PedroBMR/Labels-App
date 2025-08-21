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


class BaseWin32:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def GetDefaultPrinter(self):
        return "dummy"

    def OpenPrinter(self, name):
        return object()

    def StartDocPrinter(self, h, level, info):
        pass

    def StartPagePrinter(self, h):
        pass

    def WritePrinter(self, h, data):
        self.written.append(data)

    def EndPagePrinter(self, h):
        pass

    def EndDocPrinter(self, h):
        pass

    def ClosePrinter(self, h):
        pass


sys.modules.setdefault("win32print", BaseWin32())


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


def test_montar_tspl_expected_string(monkeypatch):
    import printing

    tpl = printing.aplicar_template("100x30")
    monkeypatch.setattr(
        printing, "melhorar_logo", lambda p, largura_desejada=240: (b"A", 1, 1)
    )
    monkeypatch.setattr(printing, "recurso_caminho", lambda p: "fake")

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
    expected = (
        f"SIZE {tpl.largura_mm} mm,{tpl.altura_mm} mm\r\n"
        f"GAP {tpl.gap_mm} mm,0\r\n"
        "DENSITY 8\r\n"
        "SPEED 4\r\n"
        f"DIRECTION {tpl.direction}\r\n"
        "CLS\r\n"
        f'TEXT {layout["titulo"]["x"]},{layout["titulo"]["y"]},"{layout["titulo"]["font"]}",0,{layout["titulo"]["xm"]},{layout["titulo"]["ym"]},"CONIMS"\r\n'
        f'TEXT {layout["saida"]["x"]},{layout["saida"]["y"]},"{layout["saida"]["font"]}",0,{layout["saida"]["xm"]},{layout["saida"]["ym"]},"Saida: S1"\r\n'
        f'TEXT {layout["categoria"]["x"]},{layout["categoria"]["y"]},"{layout["categoria"]["font"]}",0,{layout["categoria"]["xm"]},{layout["categoria"]["ym"]},"Categoria: C1"\r\n'
        f'TEXT {layout["emissor"]["x"]},{layout["emissor"]["y"]},"{layout["emissor"]["font"]}",0,{layout["emissor"]["xm"]},{layout["emissor"]["ym"]},"Emissor: E1"\r\n'
        f'TEXT {layout["municipio"]["x"]},{layout["municipio"]["y"]},"{layout["municipio"]["font"]}",0,{layout["municipio"]["xm"]},{layout["municipio"]["ym"]},"Municipio: M1"\r\n'
        f'TEXT {layout["data"]["x"]},{layout["data"]["y"]},"{layout["data"]["font"]}",0,{layout["data"]["xm"]},{layout["data"]["ym"]},"Impresso em: 2024-01-01"\r\n'
        f'TEXT {layout["fracao"]["x"]},{layout["fracao"]["y"]},"{layout["fracao"]["font"]}",0,{layout["fracao"]["xm"]},{layout["fracao"]["ym"]},"[ ] Fracao"\r\n'
        f'TEXT {layout["fragil"]["x"]},{layout["fragil"]["y"]},"{layout["fragil"]["font"]}",0,{layout["fragil"]["xm"]},{layout["fragil"]["ym"]},"[ ] Fragil"\r\n'
        f'TEXT {layout["numeracao"]["x"]},{layout["numeracao"]["y"]},"{layout["numeracao"]["font"]}",0,{layout["numeracao"]["xm"]},{layout["numeracao"]["ym"]},"1 DE 1"\r\n'
        f"BITMAP {x_logo},{layout['logo_y']},1,1,0,A\r\n"
        "PRINT 1\r\n"
    )

    assert tspl == expected


def test_printer_service_success(monkeypatch):
    import printing

    class SuccessWin32(BaseWin32):
        pass

    fake = SuccessWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    service = printing.PrinterService(printer_name="dummy")
    ok, erro = service.send("ABC")
    assert ok and erro is None
    assert fake.written == [b"ABC"]


def test_printer_service_failure(monkeypatch):
    import printing

    class FailingWin32(BaseWin32):
        def StartDocPrinter(self, h, level, info):
            raise Exception("boom")

    fake = FailingWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    service = printing.PrinterService(printer_name="dummy")
    ok, erro = service.send("XYZ")
    assert not ok
    assert erro == {"code": -1, "message": "boom"}
