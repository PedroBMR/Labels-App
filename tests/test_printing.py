"""Testes para rotinas de impressão.

Responsabilidade:
    Assegurar que comandos TSPL e envio à impressora funcionem.

Dependências:
    - printing

Exemplo:
    $ pytest tests/test_printing.py
"""

import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from printing_utils import FONT_BASE_W, text_width_dots
from tests._fake_win32 import fake_win32

sys.modules["win32print"] = fake_win32  # type: ignore[assignment]


def test_descobrir_impressora_padrao():
    import printing

    assert printing.descobrir_impressora_padrao() == "dummy"


def test_default_templates_match_assets_file():
    import json

    import printing

    path = printing.recurso_caminho("templates.json")
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    try:
        assert data == printing.DEFAULT_TEMPLATES
        expected_layouts = {
            nome: modelo["layout"] for nome, modelo in printing.DEFAULT_TEMPLATES.items()
        }
        assert printing.LAYOUTS == expected_layouts
    finally:
        printing._load_templates_json.cache_clear()


def test_printer_service_retry(monkeypatch):
    import printing

    printing.win32print.written.clear()

    count = {"n": 0}

    def start_doc(h, level, info):
        count["n"] += 1
        if count["n"] == 1:
            raise OSError("falha")

    monkeypatch.setattr(printing.win32print, "StartDocPrinter", start_doc)
    monkeypatch.setattr(printing.time, "sleep", lambda s: None)

    service = printing.PrinterService(printer_name="dummy")
    ok, erro = service.send("ABC", retry=2)

    assert ok
    assert erro is None
    assert count["n"] == 2
    assert printing.win32print.written[-1] == b"ABC"


def test_reimpressao_faltantes(fake_logo_recurso):
    import printing

    printing.win32print.written.clear()
    fake_logo_recurso.set_logo((b"ABC", 1, 1))

    total = 10
    faltantes = 3
    inicio = total - faltantes + 1

    dados = {
        "saida": "S1",
        "categoria": "Cat",
        "emissor": "Emissor",
        "municipio": "Mun",
        "volumes": faltantes,
        "data_hora": "2024-01-01",
        "inicio_indice": inicio,
        "total_exibicao": total,
    }
    tpl = printing.aplicar_template("Padrão")
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)

    assert len(printing.win32print.written) == 1
    texto = printing.win32print.written[0].decode("latin1")
    assert "8 DE 10" in texto
    assert "9 DE 10" in texto
    assert "10 DE 10" in texto


def test_reimpressao_intervalo(fake_logo_recurso):
    import printing

    fake_win32.written.clear()
    fake_logo_recurso.set_logo((b"ABC", 1, 1))

    total = 10
    inicio, fim = 5, 8
    volumes = fim - inicio + 1

    dados = {
        "saida": "S1",
        "categoria": "Cat",
        "emissor": "Emissor",
        "municipio": "Mun",
        "volumes": volumes,
        "data_hora": "2024-01-01",
        "inicio_indice": inicio,
        "total_exibicao": total,
    }
    tpl = printing.aplicar_template("Padrão")
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)

    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert "5 DE 10" in texto
    assert "8 DE 10" in texto
    assert "4 DE 10" not in texto
    assert "9 DE 10" not in texto


def test_imprimir_pagina_teste(fake_logo_recurso):
    import printing

    fake_win32.written.clear()

    tpl = printing.aplicar_template("Padrão")
    ok, erro = printing.imprimir_pagina_teste(tpl)

    assert ok
    assert erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert f"DIRECTION {tpl.direction}" in texto
    assert "1 DE 1" in texto
    dots_y = tpl.altura_mm * printing.DOTS_MM
    ruler_start = tpl.layout["titulo"]["x"]
    ruler_len = min(
        50 * printing.DOTS_MM,
        tpl.largura_mm * printing.DOTS_MM - ruler_start,
    )
    ruler_len -= ruler_len % (10 * printing.DOTS_MM)
    expected = f"BAR {ruler_start},{dots_y - 40},{ruler_len},4"
    assert expected in texto


def test_direction_personalizado(fake_logo_recurso, tmp_path):
    import printing
    fake_win32.written.clear()
    tpl_path = tmp_path / "templates.json"
    tpl_path.write_text(
        '{"60x80": {"largura_mm": 60, "altura_mm": 80, "gap_mm": 2, "direction": 0}}',
        encoding="utf-8",
    )

    def fake_recurso(p):
        return tpl_path if p == "templates.json" else "fake"

    fake_logo_recurso.set_recurso(fake_recurso)
    printing.template_manager.recarregar_templates()

    tpl = printing.aplicar_template("60x80")
    merged_templates = printing._get_templates()
    assert merged_templates["60x80"]["layout"] == printing.DEFAULT_TEMPLATES["60x80"]["layout"]

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }

    tspl = printing.montar_tspl(tpl, dados)
    assert "DIRECTION 0" in tspl

    ok, erro = printing.imprimir_pagina_teste(tpl)
    assert ok
    assert erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[0].decode("latin1")
    assert "DIRECTION 0" in texto

    printing._load_templates_json.cache_clear()


def test_templates_arquivo_inexistente(fake_logo_recurso, tmp_path, caplog):
    import printing
    fake_logo_recurso.set_recurso(lambda p: tmp_path / "inexistente.json")
    printing.template_manager.recarregar_templates()

    with caplog.at_level(logging.ERROR, logger="app"):
        from log import logger as app_logger
        app_logger.addHandler(caplog.handler)
        try:
            templates = printing.listar_templates()
        finally:
            app_logger.removeHandler(caplog.handler)

    assert templates == ["100x30", "60x80"]
    assert "templates.json" in caplog.text
    printing._load_templates_json.cache_clear()


def test_template_fallback_60x80(fake_logo_recurso):
    import printing
    fake_logo_recurso.set_recurso(lambda p: "inexistente.json")
    printing.template_manager.recarregar_templates()

    tpl = printing.aplicar_template("60x80")

    assert tpl.largura_mm == 60
    assert tpl.altura_mm == 80
    assert tpl.gap_mm == 2
    assert tpl.direction == 0

    templates = printing._get_templates()
    assert set(templates) == {"100x30", "60x80"}
    assert templates["60x80"]["layout"] == printing.DEFAULT_TEMPLATES["60x80"]["layout"]

    printing.aplicar_template("Padrão")
    printing._load_templates_json.cache_clear()


def test_templates_chave_invalida(fake_logo_recurso):
    import printing
    fake_win32.written.clear()
    printing.template_manager.recarregar_templates()
    tpl = printing.aplicar_template("inexistente")

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto

    printing.template_manager.recarregar_templates()


def test_templates_json_cache(monkeypatch, tmp_path, fake_logo_recurso):
    import json

    import printing

    file_path = tmp_path / "templates.json"
    file_path.write_text(
        '{"A": {"largura_mm":1,"altura_mm":1,"gap_mm":1,"direction":1}}',
        encoding="utf-8",
    )

    count = {"n": 0}
    original_load = json.load

    def counting_load(f):
        count["n"] += 1
        return original_load(f)

    monkeypatch.setattr(json, "load", counting_load)

    fake_logo_recurso.set_recurso(
        lambda p: file_path if p == "templates.json" else "fake"
    )

    printing.template_manager.recarregar_templates()
    assert "A" in printing.listar_templates()
    assert count["n"] == 1

    # reutiliza cache
    printing.listar_templates()
    assert count["n"] == 1

    # altera arquivo e força recarga
    file_path.write_text(
        '{"B": {"largura_mm":1,"altura_mm":1,"gap_mm":1,"direction":1}}',
        encoding="utf-8",
    )
    printing.template_manager.recarregar_templates()
    assert "B" in printing.listar_templates()
    assert count["n"] == 2

    printing._load_templates_json.cache_clear()
def test_templates_alteram_layout(fake_logo_recurso):
    import printing

    fake_win32.written.clear()
    tpl = printing.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    printing.aplicar_template("Padrão")


def test_100x30_layout(fake_logo_recurso):
    import printing

    fake_win32.written.clear()
    printing.template_manager.recarregar_templates()

    tpl = printing.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    spec = printing.LAYOUTS["100x30"]["numeracao"]
    assert f'TEXT {spec["x"]},{spec["y"]}' in texto
    printing.aplicar_template("Padrão")


def test_100x30_coordenadas(fake_logo_recurso):
    import re

    import printing

    fake_win32.written.clear()

    tpl = printing.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    max_x = tpl.largura_mm * printing.DOTS_MM
    max_y = tpl.altura_mm * printing.DOTS_MM
    for line in texto.splitlines():
        m = re.match(r"TEXT (\d+),(\d+)", line)
        if m:
            x, y = map(int, m.groups())
            assert 0 <= x <= max_x
            assert 0 <= y <= max_y
    printing.aplicar_template("Padrão")


def test_60x80_coordenadas(fake_logo_recurso):
    import re

    import printing

    fake_win32.written.clear()

    tpl = printing.aplicar_template("60x80")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)
    printing.imprimir_etiqueta(tspl)
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 60 mm,80 mm" in texto
    assert "DIRECTION 0" in texto
    max_x = tpl.largura_mm * printing.DOTS_MM
    max_y = tpl.altura_mm * printing.DOTS_MM
    for line in texto.splitlines():
        m = re.match(r"TEXT (\d+),(\d+)", line)
        if m:
            x, y = map(int, m.groups())
            assert 0 <= x <= max_x
            assert 0 <= y <= max_y
    printing.aplicar_template("Padrão")


def test_100x30_pagina_teste(fake_logo_recurso):
    import printing

    fake_win32.written.clear()
    fake_logo_recurso.set_logo(
        lambda p, largura_desejada=240: (
            b"A",
            max(1, largura_desejada // 8),
            largura_desejada,
        )
    )
    printing.template_manager.recarregar_templates()

    tpl = printing.aplicar_template("100x30")
    ok, erro = printing.imprimir_pagina_teste(tpl)
    assert ok and erro is None
    assert len(fake_win32.written) == 1
    texto = fake_win32.written[-1].decode("latin1")
    assert "SIZE 100 mm,30 mm" in texto
    assert ",15,120,0," in texto
    dots_y = tpl.altura_mm * printing.DOTS_MM
    ruler_start = tpl.layout["titulo"]["x"]
    ruler_len = min(
        50 * printing.DOTS_MM,
        tpl.largura_mm * printing.DOTS_MM - ruler_start,
    )
    ruler_len -= ruler_len % (10 * printing.DOTS_MM)
    expected = f"BAR {ruler_start},{dots_y - 40},{ruler_len},4"
    assert expected in texto
    printing.aplicar_template("Padrão")


def test_100x30_fracao_antes_de_fragil():
    import printing

    tpl = printing.aplicar_template("100x30")
    fracao_x = tpl.layout["fracao"]["x"]
    fragil_x = tpl.layout["fragil"]["x"]
    assert fracao_x < fragil_x
    printing.aplicar_template("Padrão")


def test_100x30_text_bitmap_dentro_largura(fake_logo_recurso):
    import re

    import printing

    fake_logo_recurso.set_logo((b"A", 15, 1))

    tpl = printing.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)

    max_x = tpl.largura_mm * printing.DOTS_MM
    for line in tspl.splitlines():
        if line.startswith("TEXT "):
            m = re.match(
                r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"(.*)"', line
            )
            assert m, f"Linha inesperada: {line}"
            x, _, font, xm, _, texto = m.groups()
            x, xm = int(x), int(xm)
            largura = text_width_dots(texto, font, xm)
            assert x + largura <= max_x
        elif line.startswith("BITMAP "):
            m = re.match(r'BITMAP (\d+),(\d+),(\d+),(\d+),0,', line)
            assert m, f"Linha inesperada: {line}"
            x, _, largura_b, _ = map(int, m.groups())
            assert x + largura_b * 8 <= max_x
    printing.aplicar_template("Padrão")


def test_100x30_text_bitmap_dentro_limites(fake_logo_recurso):
    import re

    import printing

    fake_logo_recurso.set_logo((b"A", 2, 16))

    tpl = printing.aplicar_template("100x30")
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tspl = printing.montar_tspl(tpl, dados)

    max_x = tpl.largura_mm * printing.DOTS_MM
    max_y = tpl.altura_mm * printing.DOTS_MM
    for line in tspl.splitlines():
        if line.startswith("TEXT "):
            m = re.match(
                r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"(.*)"', line
            )
            assert m, f"Linha inesperada: {line}"
            x, y, font, xm, ym, texto = m.groups()
            x, y, xm, ym = map(int, (x, y, xm, ym))
            largura = text_width_dots(texto, font, xm)
            altura = FONT_BASE_W.get(font, 12) * max(1, ym)
            assert x + largura <= max_x
            assert y + altura <= max_y
        elif line.startswith("BITMAP "):
            m = re.match(r'BITMAP (\d+),(\d+),(\d+),(\d+),0,', line)
            assert m, f"Linha inesperada: {line}"
            x, y, largura_b, altura = map(int, m.groups())
            assert x + largura_b * 8 <= max_x
            assert y + altura <= max_y
    printing.aplicar_template("Padrão")


def test_total_exibicao_cinco_digitos(fake_logo_recurso):
    import re

    import printing


    tpl = printing.aplicar_template("100x30")
    total = 12345
    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
        "inicio_indice": total,
        "total_exibicao": total,
    }
    tspl = printing.montar_tspl(tpl, dados)
    m = re.search(r'TEXT (\d+),(\d+),"(\d+)",0,(\d+),(\d+),"12345 DE 12345"', tspl)
    assert m, tspl
    x, _, font, xm, _ = m.groups()
    x = int(x)
    xm = int(xm)
    largura_txt = text_width_dots("12345 DE 12345", font, xm)
    max_x = tpl.largura_mm * printing.DOTS_MM
    assert x + largura_txt <= max_x
    printing.aplicar_template("Padrão")


def test_retry_exponencial_logging(monkeypatch, caplog, fake_logo_recurso):
    import logging

    import printing

    class FailingWin32:
        def __init__(self):
            self.calls = 0

        def GetDefaultPrinter(self):
            return "dummy"

        def OpenPrinter(self, name):
            return object()

        def StartDocPrinter(self, h, level, info):
            self.calls += 1
            raise RuntimeError("boom")

        def StartPagePrinter(self, h):
            pass

        def WritePrinter(self, h, data):
            pass

        def EndPagePrinter(self, h):
            pass

        def EndDocPrinter(self, h):
            pass

        def ClosePrinter(self, h):
            pass

    fake = FailingWin32()
    monkeypatch.setattr(printing, "win32print", fake)
    monkeypatch.setattr(printing.time, "sleep", lambda s: None)

    dados = {
        "saida": "S",
        "categoria": "C",
        "emissor": "E",
        "municipio": "M",
        "volumes": 1,
        "data_hora": "2024-01-01",
    }
    tpl = printing.aplicar_template("Padrão")
    tspl = printing.montar_tspl(tpl, dados)

    with caplog.at_level(logging.INFO, logger="app"):
        from log import logger as app_logger
        app_logger.addHandler(caplog.handler)
        try:
            ok, erro = printing.imprimir_etiqueta(tspl, repetir_em_falha=True)
        finally:
            app_logger.removeHandler(caplog.handler)

    assert not ok
    assert fake.calls == 3
    tentativas = [r for r in caplog.records if "Tentativa" in r.message]
    assert len(tentativas) == 3
